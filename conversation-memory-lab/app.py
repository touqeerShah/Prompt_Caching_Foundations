from __future__ import annotations

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import Any, Dict, Optional

import httpx
from fastapi import FastAPI, Query
from pydantic import BaseModel, Field
from metrics import snapshot as metrics_snapshot
from prometheus_client import make_asgi_app
from prom_metrics import record_manual_cache_review
from memory_store import (
    add_exchange,
    get_message_count,
    get_recent_messages,
    get_relevant_messages,
    get_session_debug_snapshot,
    get_turn_count,
    increment_turn_count,
    init_postgres,
    load_last_tool_result,
    load_session_meta,
    load_summary,
    load_summary_meta,
    persist_session_to_postgres,
    restore_session_from_postgres,
    save_last_tool_result,
    save_session_meta,
    save_summary,
    save_summary_meta,
    estimate_text_tokens,
)
from prompt_builder import build_prompt
from recovery import recover_session_context, FAST_MODE, FALLBACK_MODE, DEGRADED_MODE

from warmup import run_startup_warmup

from prom_metrics import record_latency, record_mode, record_summary_refresh


OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")

SUMMARY_EVERY_N_TURNS = int(os.getenv("SUMMARY_EVERY_N_TURNS", "3"))
SUMMARY_MIN_UNSUMMARIZED_TOKENS = int(
    os.getenv("SUMMARY_MIN_UNSUMMARIZED_TOKENS", "120")
)
SUMMARY_ALWAYS_ON_TOOL_RESULT = (
    os.getenv("SUMMARY_ALWAYS_ON_TOOL_RESULT", "true").lower() == "true"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    yield


@asynccontextmanager
async def lifespan(app: FastAPI):
    await init_postgres()
    warmup_stats = run_startup_warmup()
    print({"event": "startup_warmup_completed", **warmup_stats})
    yield


app = FastAPI(title="Conversation Memory Lab", lifespan=lifespan)


class ChatRequest(BaseModel):
    session_id: str
    message: str = Field(..., min_length=1)
    user_id: str = "user-123"
    tenant_id: str = "tenant-001"
    force_pg_restore: bool = False
    tool_result: Optional[Dict[str, Any]] = None


class ChatResponse(BaseModel):
    request_id: str
    session_id: str
    answer: str
    memory: Dict[str, Any]
    timings: Dict[str, float]
    prompt_preview: str


def now_ms() -> float:
    return time.perf_counter() * 1000


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
    response.raise_for_status()
    return response.json().get("response", "").strip()


async def call_ollama_generate(prompt: str, keep_alive: str = "10m") -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "keep_alive": keep_alive,
    }
    async with httpx.AsyncClient(timeout=120.0) as client:
        response = await client.post(OLLAMA_URL, json=payload)
    response.raise_for_status()
    return response.json().get("response", "").strip()


def build_summary_prompt(
    old_summary: str,
    recent_messages: list[dict[str, str]],
    user_message: str,
    answer: str,
) -> str:
    recent_block = "\n".join(
        f"{m.get('role', 'unknown').upper()}: {m.get('content', '')}"
        for m in recent_messages[-6:]
    )

    return f"""You are updating a compact conversation memory summary.

Rules:
- Keep only durable, useful context.
- Preserve decisions, preferences, constraints, facts, and unresolved tasks.
- Remove chit-chat and repetition.
- Keep the summary under 10 bullet points.
- If nothing important changed, keep the prior summary with minimal edits.

Previous summary:
{old_summary or "(none)"}

Recent conversation:
{recent_block or "(none)"}

Latest turn:
USER: {user_message}
ASSISTANT: {answer}

Return only the updated summary as bullet points.
"""


async def llm_summary_update(
    old_summary: str,
    recent_messages: list[dict[str, str]],
    user_message: str,
    answer: str,
) -> str:
    prompt = build_summary_prompt(
        old_summary=old_summary,
        recent_messages=recent_messages,
        user_message=user_message,
        answer=answer,
    )
    summary = await call_ollama_generate(prompt, keep_alive="15m")
    return summary.strip()


def recent_messages_token_estimate(messages: list[dict[str, str]]) -> int:
    return sum(estimate_text_tokens(m.get("content", "")) for m in messages)


def should_refresh_summary(
    turn_count: int,
    recent_messages: list[dict[str, str]],
    summary_meta: dict[str, Any],
    tool_result_present: bool,
) -> tuple[bool, str]:
    last_summary_turn = int(summary_meta.get("last_summary_turn", 0))

    turns_since_summary = max(0, turn_count - last_summary_turn)
    recent_tokens = recent_messages_token_estimate(recent_messages)

    if SUMMARY_ALWAYS_ON_TOOL_RESULT and tool_result_present:
        return True, "tool_result_present"

    if turns_since_summary >= SUMMARY_EVERY_N_TURNS:
        return True, f"turn_interval_reached:{turns_since_summary}"

    if recent_tokens >= SUMMARY_MIN_UNSUMMARIZED_TOKENS:
        return True, f"recent_token_threshold:{recent_tokens}"

    return False, "skipped_policy"


def naive_summary_update(old_summary: str, user_message: str, answer: str) -> str:
    addition = f"- User: {user_message}\n- Assistant: {answer}"
    if not old_summary.strip():
        return addition
    lines = (old_summary + "\n" + addition).splitlines()
    return "\n".join(lines[-12:])

@app.post("/chat", response_model=ChatResponse)
async def chat(req: ChatRequest) -> ChatResponse:
    request_id = str(uuid.uuid4())
    total_start = now_ms()

    if req.tool_result is not None:
        save_last_tool_result(req.session_id, req.tool_result)

    save_session_meta(
        req.session_id,
        {"user_id": req.user_id, "tenant_id": req.tenant_id},
    )

    recovery_start = now_ms()
    recovery = await recover_session_context(
        session_id=req.session_id,
        user_message=req.message,
        route="/chat",
    )
    recovery_ms = now_ms() - recovery_start

    recent_messages = recovery.recent_messages
    relevant_messages = recovery.relevant_messages
    summary = recovery.summary
    last_tool_result = recovery.last_tool_result
    restored_from_pg = recovery.restored_from_pg
    response_mode = recovery.mode
    degraded_reason = recovery.degraded_reason

    prompt_start = now_ms()
    if response_mode == DEGRADED_MODE:
        prompt = build_prompt(
            user_message=req.message,
            summary="",
            recent_messages=[],
            relevant_messages=[],
            last_tool_result=None,
        )
    else:
        prompt = build_prompt(
            user_message=req.message,
            summary=summary,
            recent_messages=recent_messages,
            relevant_messages=relevant_messages,
            last_tool_result=last_tool_result,
        )
    prompt_ms = now_ms() - prompt_start

    model_start = now_ms()
    answer = await call_ollama(prompt)
    model_ms = now_ms() - model_start

    write_start = now_ms()

    add_exchange(req.session_id, req.message, answer)

    turn_count = increment_turn_count(req.session_id)
    summary_meta = load_summary_meta(req.session_id)

    should_summarize, summary_reason = should_refresh_summary(
        turn_count=turn_count,
        recent_messages=recent_messages,
        summary_meta=summary_meta,
        tool_result_present=req.tool_result is not None,
    )

    summary_update_ms = 0.0
    summary_updated = False
    new_summary = summary

    if should_summarize:
        summary_update_start = now_ms()
        new_summary = await llm_summary_update(
            old_summary=summary,
            recent_messages=recent_messages,
            user_message=req.message,
            answer=answer,
        )
        summary_update_ms = now_ms() - summary_update_start

        save_summary(req.session_id, new_summary)
        save_summary_meta(
            req.session_id,
            {
                "last_summary_turn": turn_count,
                "last_summary_reason": summary_reason,
                "last_summary_tokens": estimate_text_tokens(new_summary),
            },
        )
        summary_updated = True

    await persist_session_to_postgres(req.session_id)
    write_ms = now_ms() - write_start

    total_ms = now_ms() - total_start

    source_of_truth = "postgres" if restored_from_pg else "redis"
    served_via = "redis_rehydrated_from_postgres" if restored_from_pg else "redis_hot_state"

    log_json(
        "chat_request_completed",
        {
            "request_id": request_id,
            "session_id": req.session_id,
            "mode": response_mode,
            "source_of_truth": source_of_truth,
            "served_via": served_via,
            "degraded_reason": degraded_reason,
            "summary_policy": {
                "turn_count": turn_count,
                "summary_updated": summary_updated,
                "summary_reason": summary_reason,
            },
            "timings": {
                "recovery_ms": round(recovery_ms, 2),
                **recovery.timings,
                "prompt_ms": round(prompt_ms, 2),
                "model_ms": round(model_ms, 2),
                "summary_update_ms": round(summary_update_ms, 2),
                "write_ms": round(write_ms, 2),
                "total_ms": round(total_ms, 2),
            },
            "memory_counts": {
                "recent_count": len(recent_messages),
                "relevant_count": len(relevant_messages),
            },
        },
    )

    record_mode("/chat", response_mode)
    record_latency("recovery_ms", recovery_ms, "/chat", mode=response_mode)
    record_latency("prompt_ms", prompt_ms, "/chat", mode=response_mode)
    record_latency("model_ms", model_ms, "/chat", mode=response_mode)
    record_latency("summary_update_ms", summary_update_ms, "/chat", mode=response_mode)
    record_latency("write_ms", write_ms, "/chat", mode=response_mode)
    record_latency("total_ms", total_ms, "/chat", mode=response_mode)
    record_summary_refresh("/chat", summary_updated, summary_reason)

    return ChatResponse(
        request_id=request_id,
        session_id=req.session_id,
        answer=answer,
        memory={
            "mode": response_mode,
            "restored_from_pg": restored_from_pg,
            "source_of_truth": source_of_truth,
            "served_via": served_via,
            "degraded_reason": degraded_reason,
            "recent_count": len(recent_messages),
            "relevant_count": len(relevant_messages),
            "has_summary": bool(new_summary.strip()),
            "has_tool_result": last_tool_result is not None,
            "turn_count": turn_count,
            "summary_updated": summary_updated,
            "summary_reason": summary_reason,
        },
        timings={
            "recovery_ms": round(recovery_ms, 2),
            **recovery.timings,
            "prompt_ms": round(prompt_ms, 2),
            "model_ms": round(model_ms, 2),
            "summary_update_ms": round(summary_update_ms, 2),
            "write_ms": round(write_ms, 2),
            "total_ms": round(total_ms, 2),
        },
        prompt_preview=prompt[:1800],
    )

@app.get("/session/{session_id}")
async def session_debug(
    session_id: str,
    semantic_query: str | None = Query(default=None),
    force_pg_restore: bool = Query(default=False),
) -> Dict[str, Any]:
    restored_from_pg = False

    if force_pg_restore or get_message_count(session_id) == 0:
        restored_from_pg = await restore_session_from_postgres(session_id)

    snapshot = get_session_debug_snapshot(
        session_id=session_id,
        semantic_query=semantic_query,
        recent_top_k=8,
        semantic_top_k=4,
    )

    snapshot["restored_from_pg"] = restored_from_pg
    snapshot["storage_source"] = (
        "postgres_restore" if restored_from_pg else "redis_hot_state"
    )
    return snapshot



metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)
@app.get("/metrics/debug")
async def metrics_debug() -> Dict[str, Any]:
    return metrics_snapshot()


class CacheReviewRequest(BaseModel):
    cache_type: str
    accepted: bool
    reason: str | None = None

@app.post("/cache/review")
async def review_cache_result(req: CacheReviewRequest) -> Dict[str, Any]:
    record_manual_cache_review(
        cache_type=req.cache_type,
        accepted=req.accepted,
        reason=req.reason,
    )
    return {"ok": True}