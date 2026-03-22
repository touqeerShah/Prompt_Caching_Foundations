from __future__ import annotations

import json
import time
import uuid
from typing import Any, AsyncGenerator, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field
from token_utils import best_token_count
app = FastAPI(title="LLM Foundations Starter - Streaming")

OLLAMA_STREAM_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

SYSTEM_PROMPT = """You are a helpful assistant.
Answer clearly and briefly.
If context is provided, use it.
If context is not enough, say what is missing.
"""

KNOWLEDGE_BASE = [
    {
        "id": "doc-1",
        "text": "FastAPI is a Python framework for building APIs quickly with type hints.",
    },
    {
        "id": "doc-2",
        "text": "Ollama can run language models locally and expose them over an HTTP API.",
    },
    {
        "id": "doc-3",
        "text": "Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic.",
    },
]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_retrieval: bool = True


class TimingBreakdown(BaseModel):
    retrieval_ms: float
    prompt_assembly_ms: float
    ttft_ms: Optional[float]
    model_total_ms: float
    total_ms: float


class ChatResponse(BaseModel):
    request_id: str
    model: str
    answer: str
    prompt_preview: str
    prompt_stats: Dict[str, Any]
    timings: TimingBreakdown
    retrieved_docs: List[Dict[str, Any]]


def now_ms() -> float:
    return time.perf_counter() * 1000


def estimate_token_count(text: str) -> int:
    return max(1, len(text.split()))


def log_json(event: str, payload: Dict[str, Any]) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False))


def simple_retrieve(query: str, top_k: int = 2) -> List[Dict[str, Any]]:
    q_terms = set(query.lower().split())
    scored: List[tuple[int, Dict[str, Any]]] = []

    for doc in KNOWLEDGE_BASE:
        d_terms = set(doc["text"].lower().split())
        score = len(q_terms.intersection(d_terms))
        if score > 0:
            scored.append((score, doc))

    scored.sort(key=lambda x: x[0], reverse=True)
    return [doc for _, doc in scored[:top_k]]


def build_prompt(
    system_prompt: str,
    user_message: str,
    retrieved_docs: Optional[List[Dict[str, Any]]] = None,
) -> str:
    parts: List[str] = [f"[SYSTEM]\n{system_prompt.strip()}"]

    if retrieved_docs:
        context_lines = "\n".join(
            f"- ({doc['id']}) {doc['text']}" for doc in retrieved_docs
        )
        parts.append(f"[CONTEXT]\n{context_lines}")

    parts.append(f"[USER]\n{user_message.strip()}")
    parts.append("[ASSISTANT]\n")

    return "\n\n".join(parts)


async def stream_ollama(prompt: str) -> Dict[str, Any]:
    """
    Streams from Ollama and measures TTFT.

    Returns:
        {
            "answer": str,
            "ttft_ms": float | None,
            "model_total_ms": float
        }
    """
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": True,
    }

    full_text_parts: List[str] = []
    ttft_ms: Optional[float] = None
    model_start = now_ms()

    async with httpx.AsyncClient(timeout=120.0) as client:
        async with client.stream("POST", OLLAMA_STREAM_URL, json=payload) as response:
            if response.status_code != 200:
                body = await response.aread()
                raise HTTPException(
                    status_code=502,
                    detail=f"Ollama error: {response.status_code} {body.decode(errors='ignore')}",
                )

            async for line in response.aiter_lines():
                if not line.strip():
                    continue

                try:
                    chunk = json.loads(line)
                except json.JSONDecodeError:
                    continue

                text_piece = chunk.get("response", "")

                # TTFT: first non-empty generated text chunk
                if text_piece and ttft_ms is None:
                    ttft_ms = now_ms() - model_start

                if text_piece:
                    full_text_parts.append(text_piece)

                if chunk.get("done", False):
                    break

    model_total_ms = now_ms() - model_start

    return {
        "answer": "".join(full_text_parts).strip(),
        "ttft_ms": round(ttft_ms, 2) if ttft_ms is not None else None,
        "model_total_ms": round(model_total_ms, 2),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_id = str(uuid.uuid4())
    total_start = now_ms()

    # 1) Retrieval
    retrieval_start = now_ms()
    retrieved_docs: List[Dict[str, Any]] = []
    if req.use_retrieval:
        retrieved_docs = simple_retrieve(req.message)
    retrieval_ms = now_ms() - retrieval_start

    # 2) Prompt assembly
    prompt_start = now_ms()
    prompt = build_prompt(
        system_prompt=SYSTEM_PROMPT,
        user_message=req.message,
        retrieved_docs=retrieved_docs,
    )
    prompt_assembly_ms = now_ms() - prompt_start

    # 3) Streaming model call + TTFT
    model_result = await stream_ollama(prompt)
    answer = model_result["answer"]
    ttft_ms = model_result["ttft_ms"]
    model_total_ms = model_result["model_total_ms"]

    total_ms = now_ms() - total_start

    total_token_info = best_token_count(prompt)
    system_token_info = best_token_count(SYSTEM_PROMPT)
    context_text = "\n".join(doc["text"] for doc in retrieved_docs) if retrieved_docs else ""
    context_token_info = best_token_count(context_text) if context_text else {
        "tokenizer_name": total_token_info["tokenizer_name"],
        "count": 0,
        "count_method": total_token_info["count_method"],
    }
    user_token_info = best_token_count(req.message)

    prompt_stats = {
        "total_tokens": total_token_info["count"],
        "system_tokens": system_token_info["count"],
        "context_tokens": context_token_info["count"],
        "user_tokens": user_token_info["count"],
        "tokenizer_name": total_token_info["tokenizer_name"],
        "count_method": total_token_info["count_method"],
        "has_retrieval_context": bool(retrieved_docs),
    }

    log_json(
        "chat_request_completed",
        {
            "request_id": request_id,
            "model": MODEL_NAME,
            "message": req.message,
            "timings": {
                "retrieval_ms": round(retrieval_ms, 2),
                "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                "ttft_ms": ttft_ms,
                "model_total_ms": model_total_ms,
                "total_ms": round(total_ms, 2),
            },
            "prompt_stats": prompt_stats,
            "retrieved_doc_ids": [doc["id"] for doc in retrieved_docs],
        },
    )

    return ChatResponse(
        request_id=request_id,
        model=MODEL_NAME,
        answer=answer,
        prompt_preview=prompt[:1200],
        prompt_stats=prompt_stats,
        timings=TimingBreakdown(
            retrieval_ms=round(retrieval_ms, 2),
            prompt_assembly_ms=round(prompt_assembly_ms, 2),
            ttft_ms=ttft_ms,
            model_total_ms=model_total_ms,
            total_ms=round(total_ms, 2),
        ),
        retrieved_docs=retrieved_docs,
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}
