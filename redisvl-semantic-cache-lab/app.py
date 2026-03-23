from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from redisvl.query.filter import Tag

from semantic_cache_utils import (
    build_semantic_prompt,
    cache_metadata,
    make_cache,
)

app = FastAPI(title="RedisVL Semantic Cache Lab")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

semantic_cache = make_cache()


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    tenant_id: str = "tenant-001"
    language: str = "en"
    version: str = "v1"
    category: str = "faq"
    use_semantic_cache: bool = True
    distance_threshold: Optional[float] = None


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    semantic_cache: Dict[str, Any]
    timings: Dict[str, float]
    prompt_stats: Dict[str, Any]


def now_ms() -> float:
    return time.perf_counter() * 1000


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def log_json(event: str, payload: Dict[str, Any]) -> None:
    row = json.dumps({"event": event, **payload}, ensure_ascii=False)
    print(row)
    with open("logs.jsonl", "a", encoding="utf-8") as f:
        f.write(row + "\n")


async def call_ollama(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
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

    prompt_start = now_ms()
    prompt = build_semantic_prompt(req.message, category=req.category)
    meta = cache_metadata(
        tenant_id=req.tenant_id,
        language=req.language,
        version=req.version,
        category=req.category,
    )
    prompt_assembly_ms = now_ms() - prompt_start

    cache_lookup_ms = 0.0
    cache_write_ms = 0.0
    model_ms = 0.0

    filter_expr = (
        (Tag("tenant_id") == req.tenant_id)
        & (Tag("language") == req.language)
        & (Tag("version") == req.version)
        & (Tag("category") == req.category)
    )

    cached_result = None
    if req.use_semantic_cache:
        lookup_start = now_ms()
        cached_result = semantic_cache.check(
            prompt=prompt,
            filter_expression=filter_expr,
            distance_threshold=req.distance_threshold,
            num_results=1,
        )
        cache_lookup_ms = now_ms() - lookup_start

    if cached_result:
        # SemanticCache returns matched entries with response and metadata
        hit = cached_result[0] if isinstance(cached_result, list) else cached_result
        answer = hit.get("response", "")
        distance = hit.get("vector_distance")

        total_ms = now_ms() - total_start

        log_json(
            "chat_request_completed",
            {
                "request_id": request_id,
                "semantic_cache_hit": True,
                "distance": distance,
                "timings": {
                    "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                    "cache_lookup_ms": round(cache_lookup_ms, 2),
                    "model_ms": 0.0,
                    "cache_write_ms": 0.0,
                    "total_ms": round(total_ms, 2),
                },
                "metadata": meta,
            },
        )

        return ChatResponse(
            request_id=request_id,
            answer=answer,
            semantic_cache={
                "hit": True,
                "distance": distance,
                "metadata_scope": meta,
            },
            timings={
                "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                "cache_lookup_ms": round(cache_lookup_ms, 2),
                "model_ms": 0.0,
                "cache_write_ms": 0.0,
                "total_ms": round(total_ms, 2),
            },
            prompt_stats={
                "estimated_prompt_tokens": estimate_tokens(prompt),
                "prompt_chars": len(prompt),
            },
        )

    model_start = now_ms()
    answer = await call_ollama(prompt)
    model_ms = now_ms() - model_start

    if req.use_semantic_cache:
        write_start = now_ms()
        semantic_cache.store(
            prompt=prompt,
            response=answer,
            metadata=meta,
        )
        cache_write_ms = now_ms() - write_start

    total_ms = now_ms() - total_start

    log_json(
        "chat_request_completed",
        {
            "request_id": request_id,
            "semantic_cache_hit": False,
            "distance": None,
            "timings": {
                "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                "cache_lookup_ms": round(cache_lookup_ms, 2),
                "model_ms": round(model_ms, 2),
                "cache_write_ms": round(cache_write_ms, 2),
                "total_ms": round(total_ms, 2),
            },
            "metadata": meta,
        },
    )

    return ChatResponse(
        request_id=request_id,
        answer=answer,
        semantic_cache={
            "hit": False,
            "distance": None,
            "metadata_scope": meta,
        },
        timings={
            "prompt_assembly_ms": round(prompt_assembly_ms, 2),
            "cache_lookup_ms": round(cache_lookup_ms, 2),
            "model_ms": round(model_ms, 2),
            "cache_write_ms": round(cache_write_ms, 2),
            "total_ms": round(total_ms, 2),
        },
        prompt_stats={
            "estimated_prompt_tokens": estimate_tokens(prompt),
            "prompt_chars": len(prompt),
        },
    )


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}