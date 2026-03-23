# build canonical prompt
# hash prompt
# check Redis
# if hit, return cached answer
# if miss, call Ollama
# store result in Redis with TTL
from __future__ import annotations

import json
import os
import time
import uuid
from typing import Any, Dict, Optional

import httpx
import redis
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from prompt_utils import build_canonical_prompt, prompt_hash

app = FastAPI(title="Redis Exact Cache Lab")

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", "6379"))
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "3600"))

r = redis.Redis(host=REDIS_HOST, port=REDIS_PORT, decode_responses=True)


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    context: str = ""
    use_cache: bool = True


class ChatResponse(BaseModel):
    request_id: str
    answer: str
    cache: Dict[str, Any]
    timings: Dict[str, float]
    prompt_stats: Dict[str, Any]


def now_ms() -> float:
    return time.perf_counter() * 1000


def log_json(event: str, payload: Dict[str, Any]) -> None:
    row = json.dumps({"event": event, **payload}, ensure_ascii=False)
    print(row)
    with open("logs.jsonl", "a", encoding="utf-8") as f:
        f.write(row + "\n")


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


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
    prompt = build_canonical_prompt(req.message, req.context)
    cache_key = f"exact_cache:{prompt_hash(prompt)}"
    prompt_assembly_ms = now_ms() - prompt_start

    cache_lookup_start = now_ms()
    cached_answer: Optional[str] = None
    if req.use_cache:
        cached_answer = r.get(cache_key)
    cache_lookup_ms = now_ms() - cache_lookup_start

    if cached_answer is not None:
        total_ms = now_ms() - total_start

        log_json(
            "chat_request_completed",
            {
                "request_id": request_id,
                "cache_hit": True,
                "cache_key": cache_key,
                "timings": {
                    "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                    "cache_lookup_ms": round(cache_lookup_ms, 2),
                    "model_ms": 0.0,
                    "cache_write_ms": 0.0,
                    "total_ms": round(total_ms, 2),
                },
            },
        )

        return ChatResponse(
            request_id=request_id,
            answer=cached_answer,
            cache={
                "hit": True,
                "key": cache_key,
                "ttl_seconds": r.ttl(cache_key),
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

    cache_write_start = now_ms()
    if req.use_cache:
        r.setex(cache_key, CACHE_TTL_SECONDS, answer)
    cache_write_ms = now_ms() - cache_write_start

    total_ms = now_ms() - total_start

    log_json(
        "chat_request_completed",
        {
            "request_id": request_id,
            "cache_hit": False,
            "cache_key": cache_key,
            "timings": {
                "prompt_assembly_ms": round(prompt_assembly_ms, 2),
                "cache_lookup_ms": round(cache_lookup_ms, 2),
                "model_ms": round(model_ms, 2),
                "cache_write_ms": round(cache_write_ms, 2),
                "total_ms": round(total_ms, 2),
            },
        },
    )

    return ChatResponse(
        request_id=request_id,
        answer=answer,
        cache={
            "hit": False,
            "key": cache_key,
            "ttl_seconds": CACHE_TTL_SECONDS if req.use_cache else None,
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