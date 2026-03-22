from __future__ import annotations

import json
import time
import uuid
from typing import Any, Dict, List, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from prompt_lab import (
    build_prompt_version_a,
    build_prompt_version_b,
    build_prompt_version_c,
    prompt_metrics,
)
from token_utils import best_token_count

app = FastAPI(title="LLM Prompt Reuse Lab")

OLLAMA_STREAM_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5-coder:7b"

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
    {
        "id": "doc-4",
        "text": "Prompt caching works best when the repeated prefix remains identical across calls.",
    },
]


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    use_retrieval: bool = True
    prompt_version: str = Field(default="c", pattern="^[abc]$")
    user_id: str = "user-123"
    inject_whitespace_noise: bool = False
    tenant_id: str = "tenant-001"


class TimingBreakdown(BaseModel):
    retrieval_ms: float
    prompt_assembly_ms: float
    ttft_ms: Optional[float]
    model_total_ms: float
    total_ms: float


class ChatResponse(BaseModel):
    request_id: str
    model: str
    prompt_version: str
    answer: str
    prompt_preview: str
    prompt_stats: Dict[str, Any]
    timings: TimingBreakdown
    retrieved_docs: List[Dict[str, Any]]


def now_ms() -> float:
    return time.perf_counter() * 1000


def log_json(event: str, payload: Dict[str, Any]) -> None:
    row = json.dumps({"event": event, **payload}, ensure_ascii=False)
    print(row)
    with open("logs.jsonl", "a", encoding="utf-8") as f:
        f.write(row + "\n")


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


def build_tenant_config(user_id: str, tenant_id: str) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "user_id": user_id,
        "language": "en",
        "persona": "support_assistant",
        "region": "eu",
    }


def build_prompt_by_version(
    prompt_version: str,
    user_message: str,
    retrieved_docs: List[Dict[str, Any]],
    tenant_config: Dict[str, Any],
) -> Dict[str, str]:
    if prompt_version == "a":
        return build_prompt_version_a(user_message, retrieved_docs, tenant_config)
    if prompt_version == "b":
        return build_prompt_version_b(user_message, retrieved_docs, tenant_config)
    return build_prompt_version_c(user_message, retrieved_docs, tenant_config)


def add_whitespace_noise(text: str) -> str:
    return f"  \n\n{text}\n   \n"


async def stream_ollama(prompt: str) -> Dict[str, Any]:
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

    retrieval_start = now_ms()
    retrieved_docs: List[Dict[str, Any]] = []

    message_for_prompt = req.message
    # print(f"Received message: {req}")
    if getattr(req, "inject_whitespace_noise", False):
        print("Injecting whitespace noise into the user message for testing purposes.")
        message_for_prompt = add_whitespace_noise(req.message)
    if req.use_retrieval:
        retrieved_docs = simple_retrieve(message_for_prompt)
    retrieval_ms = now_ms() - retrieval_start

    prompt_start = now_ms()
    tenant_config = build_tenant_config(req.user_id, req.tenant_id)
    prompt_parts = build_prompt_by_version(
        req.prompt_version,
        message_for_prompt,
        retrieved_docs,
        tenant_config,
    )
    prompt = prompt_parts["full_prompt"]
    static_prefix = prompt_parts["static_prefix"]
    prompt_assembly_ms = now_ms() - prompt_start

    model_result = await stream_ollama(prompt)
    answer = model_result["answer"]
    ttft_ms = model_result["ttft_ms"]
    model_total_ms = model_result["model_total_ms"]

    total_ms = now_ms() - total_start

    total_token_info = best_token_count(prompt)
    static_prefix_token_info = best_token_count(static_prefix) if static_prefix else {
        "tokenizer_name": total_token_info["tokenizer_name"],
        "count": 0,
        "count_method": total_token_info["count_method"],
    }

    prompt_info = prompt_metrics(prompt, static_prefix)

    prompt_stats = {
        "prompt_version": req.prompt_version,
        "total_tokens": total_token_info["count"],
        "static_prefix_tokens": static_prefix_token_info["count"],
        "tokenizer_name": total_token_info["tokenizer_name"],
        "count_method": total_token_info["count_method"],
        "has_retrieval_context": bool(retrieved_docs),
        **prompt_info,
    }

    log_json(
        "chat_request_completed",
        {
            "request_id": request_id,
            "model": MODEL_NAME,
            "prompt_version": req.prompt_version,
            "message": message_for_prompt,
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
        prompt_version=req.prompt_version,
        answer=answer,
        prompt_preview=prompt[:1500],
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