from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional

from tenacity import retry, stop_after_attempt, wait_random_exponential

from memory_store import (
    get_recent_messages,
    get_relevant_messages,
    load_last_tool_result,
    load_summary,
    restore_session_from_postgres,
)
# from metrics import record_cache_hit, record_latency, record_mode
from prom_metrics import record_cache_hit, record_latency, record_mode
FAST_MODE = "fast"
FALLBACK_MODE = "fallback"
DEGRADED_MODE = "degraded"


@dataclass
class RecoveryResult:
    mode: str
    restored_from_pg: bool
    used_semantic_recall: bool
    degraded_reason: Optional[str]
    recent_messages: list[dict[str, Any]]
    relevant_messages: list[dict[str, Any]]
    summary: str
    last_tool_result: Optional[dict[str, Any]]
    timings: dict[str, float]


def now_ms() -> float:
    return time.perf_counter() * 1000


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random_exponential(multiplier=0.2, max=2),
    reraise=True,
)
def safe_get_recent_messages(session_id: str, top_k: int = 8):
    return get_recent_messages(session_id, top_k=top_k)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(multiplier=0.2, max=1),
    reraise=True,
)
def safe_load_summary(session_id: str):
    return load_summary(session_id)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(multiplier=0.2, max=1),
    reraise=True,
)
def safe_load_last_tool_result(session_id: str):
    return load_last_tool_result(session_id)


@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(multiplier=0.3, max=2),
    reraise=True,
)
def safe_get_relevant_messages(session_id: str, prompt: str, top_k: int = 4):
    return get_relevant_messages(
        session_id=session_id,
        prompt=prompt,
        top_k=top_k,
        fall_back=True,
    )


@retry(
    stop=stop_after_attempt(2),
    wait=wait_random_exponential(multiplier=0.4, max=2),
    reraise=True,
)
async def safe_restore_from_postgres(session_id: str) -> bool:
    return await restore_session_from_postgres(session_id)

async def recover_session_context(
    session_id: str,
    user_message: str,
    route: str = "/chat",
) -> RecoveryResult:
    timings: dict[str, float] = {}
    restored_from_pg = False
    used_semantic_recall = False
    failure_reasons: list[str] = []

    def run_semantic_recall() -> tuple[list[dict[str, Any]], bool, float]:
        semantic_start = now_ms()
        try:
            relevant = safe_get_relevant_messages(session_id, user_message, top_k=4)
            semantic_ms = now_ms() - semantic_start
            record_latency("semantic_lookup_ms", semantic_ms, route)

            used = bool(relevant)
            record_cache_hit(
                "semantic_memory",
                route,
                hit=used,
                reason="not_found" if not used else None,
            )
            return relevant, used, round(semantic_ms, 2)
        except Exception as exc:
            semantic_ms = now_ms() - semantic_start
            record_latency("semantic_lookup_ms", semantic_ms, route)
            record_cache_hit(
                "semantic_memory",
                route,
                hit=False,
                reason=f"lookup_failed:{type(exc).__name__}",
            )
            return [], False, round(semantic_ms, 2)

    # 1) Redis hot path
    redis_start = now_ms()
    try:
        recent_messages = safe_get_recent_messages(session_id, top_k=8)
        summary = safe_load_summary(session_id)
        last_tool_result = safe_load_last_tool_result(session_id)

        redis_hot_ms = now_ms() - redis_start
        timings["redis_hot_ms"] = round(redis_hot_ms, 2)
        record_latency("redis_hot_ms", redis_hot_ms, route)

        if recent_messages or summary or last_tool_result:
            record_cache_hit("session_hot_state", route, hit=True)

            relevant_messages, used_semantic_recall, semantic_ms = run_semantic_recall()
            timings["semantic_lookup_ms"] = semantic_ms

            record_mode(route, FAST_MODE)

            return RecoveryResult(
                mode=FAST_MODE,
                restored_from_pg=False,
                used_semantic_recall=used_semantic_recall,
                degraded_reason=None,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                summary=summary,
                last_tool_result=last_tool_result,
                timings=timings,
            )

        record_cache_hit("session_hot_state", route, hit=False, reason="not_found")

    except Exception as exc:
        redis_hot_ms = now_ms() - redis_start
        timings["redis_hot_ms"] = round(redis_hot_ms, 2)
        record_latency("redis_hot_ms", redis_hot_ms, route)
        record_cache_hit(
            "session_hot_state",
            route,
            hit=False,
            reason=f"source_unavailable:{type(exc).__name__}",
        )
        failure_reasons.append(f"redis_hot_failed:{type(exc).__name__}")

    # 2) Postgres fallback
    pg_start = now_ms()
    try:
        restored_from_pg = await safe_restore_from_postgres(session_id)
        pg_restore_ms = now_ms() - pg_start
        timings["pg_restore_ms"] = round(pg_restore_ms, 2)
        record_latency("pg_restore_ms", pg_restore_ms, route)

        if restored_from_pg:
            record_cache_hit("postgres_fallback", route, hit=True)

            recent_messages = safe_get_recent_messages(session_id, top_k=8)
            summary = safe_load_summary(session_id)
            last_tool_result = safe_load_last_tool_result(session_id)

            relevant_messages, used_semantic_recall, semantic_ms = run_semantic_recall()
            timings["semantic_lookup_ms"] = semantic_ms

            record_mode(route, FALLBACK_MODE)

            return RecoveryResult(
                mode=FALLBACK_MODE,
                restored_from_pg=True,
                used_semantic_recall=used_semantic_recall,
                degraded_reason=None,
                recent_messages=recent_messages,
                relevant_messages=relevant_messages,
                summary=summary,
                last_tool_result=last_tool_result,
                timings=timings,
            )

        record_cache_hit("postgres_fallback", route, hit=False, reason="not_found")

    except Exception as exc:
        pg_restore_ms = now_ms() - pg_start
        timings["pg_restore_ms"] = round(pg_restore_ms, 2)
        record_latency("pg_restore_ms", pg_restore_ms, route)
        record_cache_hit(
            "postgres_fallback",
            route,
            hit=False,
            reason=f"source_unavailable:{type(exc).__name__}",
        )
        failure_reasons.append(f"pg_restore_failed:{type(exc).__name__}")

    # 3) degraded mode
    degraded_reason = (
        ";".join(failure_reasons) if failure_reasons else "all_recovery_sources_unavailable"
    )

    record_mode(route, DEGRADED_MODE)
    record_cache_hit("recovery_chain", route, hit=False, reason=degraded_reason)

    return RecoveryResult(
        mode=DEGRADED_MODE,
        restored_from_pg=False,
        used_semantic_recall=False,
        degraded_reason=degraded_reason,
        recent_messages=[],
        relevant_messages=[],
        summary="",
        last_tool_result=None,
        timings=timings,
    )