from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="LLM Foundations Starter")

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

# -----------------------------
# 1) Static prefix / system prompt
# -----------------------------
SYSTEM_PROMPT = """You are a helpful assistant.
Answer clearly and briefly.
If context is provided, use it.
If context is not enough, say what is missing.
"""

# -----------------------------
# 2) Tiny local retrieval stub
#    This simulates a future RAG layer.
# -----------------------------
KNOWLEDGE_BASE = [
    {
        "id": "doc-1",
        "text": "FastAPI is a Python framework for building APIs quickly with type hints."
    },
    {
        "id": "doc-2",
        "text": "Ollama can run language models locally and expose them over an HTTP API."
    },
    {
        "id": "doc-3",
        "text": "Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic."
    },
]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_retrieval: bool = True


class TimingBreakdown(BaseModel):
    retrieval_ms: float
    prompt_assembly_ms: float
    model_ms: float
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
    """
    Very rough approximation for learning purposes only.
    Real token counts depend on the model tokenizer.
    """
    return max(1, len(text.split()))


def log_json(event: str, payload: Dict[str, Any]) -> None:
    print(json.dumps({"event": event, **payload}, ensure_ascii=False))


def simple_retrieve(query: str, top_k: int = 2) -> List[Dict[str, Any]]:
    """
    Very naive keyword-overlap retrieval.
    Good enough for foundations practice.
    """
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
    """
    Prompt structure:
    1. Static prefix
    2. Optional dynamic retrieved context
    3. Dynamic user question
    """
    parts: List[str] = [f"[SYSTEM]\n{system_prompt.strip()}"]

    if retrieved_docs:
        context_lines = "\n".join(
            f"- ({doc['id']}) {doc['text']}" for doc in retrieved_docs
        )
        parts.append(f"[CONTEXT]\n{context_lines}")

    parts.append(f"[USER]\n{user_message.strip()}")
    parts.append("[ASSISTANT]\n")

    return "\n\n".join(parts)


async def call_ollama(prompt: str) -> str:
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
    }

    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Ollama error: {response.status_code} {response.text}",
        )

    data = response.json()
    return data.get("response", "").strip()


@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_id = str(uuid.uuid4())
    total_start = now_ms()

    # -----------------------------
    # Step 1: Retrieval
    # -----------------------------
    retrieval_start = now_ms()
    retrieved_docs: List[Dict[str, Any]] = []

    if req.use_retrieval:
        retrieved_docs = simple_retrieve(req.message)

    retrieval_ms = now_ms() - retrieval_start

    # -----------------------------
    # Step 2: Prompt assembly
    # -----------------------------
    prompt_start = now_ms()
    prompt = build_prompt(
        system_prompt=SYSTEM_PROMPT,
        user_message=req.message,
        retrieved_docs=retrieved_docs,
    )
    prompt_assembly_ms = now_ms() - prompt_start

    # -----------------------------
    # Step 3: Model call
    # -----------------------------
    model_start = now_ms()
    answer = await call_ollama(prompt)
    model_ms = now_ms() - model_start

    total_ms = now_ms() - total_start

    prompt_stats = {
        "estimated_total_tokens": estimate_token_count(prompt),
        "estimated_system_tokens": estimate_token_count(SYSTEM_PROMPT),
        "estimated_context_tokens": estimate_token_count(
            "\n".join(doc["text"] for doc in retrieved_docs)
        ) if retrieved_docs else 0,
        "estimated_user_tokens": estimate_token_count(req.message),
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
                "model_ms": round(model_ms, 2),
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
            model_ms=round(model_ms, 2),
            total_ms=round(total_ms, 2),
        ),
        retrieved_docs=retrieved_docs,
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}