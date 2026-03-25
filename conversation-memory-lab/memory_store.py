from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import asyncpg
import redis
from redisvl.extensions.message_history import MessageHistory, SemanticMessageHistory
from redisvl.utils.vectorize import HFTextVectorizer
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError


REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379")
PG_DSN = os.getenv("PG_DSN", "postgresql://postgres:postgres@localhost:5432/memorylab")
SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "3600"))
redis_client = redis.Redis.from_url(
    REDIS_URL,
    decode_responses=True,
    retry=Retry(ExponentialBackoff(cap=1, base=0.05), 3),
    retry_on_error=[ConnectionError, TimeoutError],
)
# redis_client = redis.Redis.from_url(REDIS_URL, decode_responses=True)

vectorizer = HFTextVectorizer(model="sentence-transformers/all-MiniLM-L6-v2")

recent_history = MessageHistory(
    name="chat_recent_history",
    redis_url=REDIS_URL,
)

semantic_history = SemanticMessageHistory(
    name="chat_semantic_history",
    redis_url=REDIS_URL,
    vectorizer=vectorizer,
    distance_threshold=0.3,
    overwrite=False,
)


def session_summary_key(session_id: str) -> str:
    return f"session:{session_id}:summary"


def session_tool_key(session_id: str) -> str:
    return f"session:{session_id}:last_tool"


def session_meta_key(session_id: str) -> str:
    return f"session:{session_id}:meta"


def set_with_ttl(key: str, value: str, ttl: int = SESSION_TTL_SECONDS) -> None:
    redis_client.setex(key, ttl, value)


def touch_session(session_id: str, ttl: int = SESSION_TTL_SECONDS) -> None:
    for key in [
        session_summary_key(session_id),
        session_tool_key(session_id),
        session_meta_key(session_id),
        session_turn_count_key(session_id),
        session_summary_meta_key(session_id),
    ]:
        if redis_client.exists(key):
            redis_client.expire(key, ttl)


def session_turn_count_key(session_id: str) -> str:
    return f"session:{session_id}:turn_count"


def session_summary_meta_key(session_id: str) -> str:
    return f"session:{session_id}:summary_meta"


def increment_turn_count(session_id: str) -> int:
    value = redis_client.incr(session_turn_count_key(session_id))
    redis_client.expire(session_turn_count_key(session_id), SESSION_TTL_SECONDS)
    return int(value)


def get_turn_count(session_id: str) -> int:
    value = redis_client.get(session_turn_count_key(session_id))
    return int(value) if value else 0


def save_summary_meta(session_id: str, meta: Dict[str, Any]) -> None:
    set_with_ttl(
        session_summary_meta_key(session_id), json.dumps(meta, ensure_ascii=False)
    )


def load_summary_meta(session_id: str) -> Dict[str, Any]:
    raw = redis_client.get(session_summary_meta_key(session_id))
    return json.loads(raw) if raw else {}


def estimate_text_tokens(text: str) -> int:
    return max(1, len(text.split())) if text and text.strip() else 0


def save_summary(session_id: str, summary: str) -> None:
    set_with_ttl(session_summary_key(session_id), summary)


def load_summary(session_id: str) -> str:
    return redis_client.get(session_summary_key(session_id)) or ""


def save_last_tool_result(session_id: str, tool_result: Dict[str, Any]) -> None:
    set_with_ttl(
        session_tool_key(session_id), json.dumps(tool_result, ensure_ascii=False)
    )


def load_last_tool_result(session_id: str) -> Optional[Dict[str, Any]]:
    raw = redis_client.get(session_tool_key(session_id))
    return json.loads(raw) if raw else None


def save_session_meta(session_id: str, meta: Dict[str, Any]) -> None:
    set_with_ttl(session_meta_key(session_id), json.dumps(meta, ensure_ascii=False))


def load_session_meta(session_id: str) -> Optional[Dict[str, Any]]:
    raw = redis_client.get(session_meta_key(session_id))
    return json.loads(raw) if raw else None


def add_message(session_id: str, role: str, content: str) -> None:
    message = {"role": role, "content": content}
    recent_history.add_message(message, session_tag=session_id)
    semantic_history.add_message(message, session_tag=session_id)
    touch_session(session_id)


def add_exchange(session_id: str, user_message: str, assistant_message: str) -> None:
    recent_history.store(user_message, assistant_message, session_tag=session_id)
    semantic_history.store(user_message, assistant_message, session_tag=session_id)
    touch_session(session_id)


def get_recent_messages(session_id: str, top_k: int = 8) -> List[Dict[str, str]]:
    return recent_history.get_recent(top_k=top_k, session_tag=session_id, raw=True)


def get_relevant_messages(
    session_id: str,
    prompt: str,
    top_k: int = 4,
    fall_back: bool = True,
) -> List[Dict[str, str]]:
    return semantic_history.get_relevant(
        prompt=prompt,
        top_k=top_k,
        session_tag=session_id,
        raw=True,
        fall_back=fall_back,
    )


def get_message_count(session_id: str) -> int:
    return recent_history.count(session_tag=session_id)


async def init_postgres() -> None:
    conn = await asyncpg.connect(PG_DSN)
    try:
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                summary TEXT DEFAULT '',
                last_tool_result JSONB,
                meta JSONB,
                updated_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_messages (
                id BIGSERIAL PRIMARY KEY,
                session_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TIMESTAMPTZ DEFAULT NOW()
            );
            """
        )
    finally:
        await conn.close()


async def persist_session_to_postgres(session_id: str) -> None:
    conn = await asyncpg.connect(PG_DSN)
    try:
        summary = load_summary(session_id)
        last_tool = load_last_tool_result(session_id)
        meta = load_session_meta(session_id) or {}

        await conn.execute(
            """
            INSERT INTO chat_sessions(session_id, summary, last_tool_result, meta, updated_at)
            VALUES($1, $2, $3::jsonb, $4::jsonb, NOW())
            ON CONFLICT(session_id)
            DO UPDATE SET
                summary = EXCLUDED.summary,
                last_tool_result = EXCLUDED.last_tool_result,
                meta = EXCLUDED.meta,
                updated_at = NOW()
            """,
            session_id,
            summary,
            json.dumps(last_tool) if last_tool is not None else None,
            json.dumps(meta),
        )

        messages = get_recent_messages(session_id, top_k=100)
        await conn.execute(
            "DELETE FROM chat_messages WHERE session_id = $1", session_id
        )

        for msg in messages:
            await conn.execute(
                """
                INSERT INTO chat_messages(session_id, role, content)
                VALUES($1, $2, $3)
                """,
                session_id,
                msg["role"],
                msg["content"],
            )
    finally:
        await conn.close()

async def restore_session_from_postgres(session_id: str) -> bool:
    conn = await asyncpg.connect(PG_DSN)
    try:
        session_row = await conn.fetchrow(
            "SELECT session_id, summary, last_tool_result, meta FROM chat_sessions WHERE session_id = $1",
            session_id,
        )
        if not session_row:
            return False

        messages = await conn.fetch(
            """
            SELECT role, content
            FROM chat_messages
            WHERE session_id = $1
            ORDER BY created_at ASC, id ASC
            """,
            session_id,
        )

        summary = session_row["summary"]
        if summary:
            save_summary(session_id, summary)

        last_tool_result = session_row["last_tool_result"]
        if last_tool_result is not None:
            save_last_tool_result(session_id, last_tool_result)

        meta = session_row["meta"]
        if meta is not None:
            save_session_meta(session_id, meta)

        for msg in messages:
            add_message(session_id, msg["role"], msg["content"])

        return True
    finally:
        await conn.close()


def get_session_debug_snapshot(
    session_id: str,
    semantic_query: Optional[str] = None,
    recent_top_k: int = 8,
    semantic_top_k: int = 4,
) -> Dict[str, Any]:
    recent_messages = get_recent_messages(session_id, top_k=recent_top_k)
    summary = load_summary(session_id)
    last_tool_result = load_last_tool_result(session_id)
    meta = load_session_meta(session_id)
    summary_meta = load_summary_meta(session_id)
    semantic_matches = []

    if semantic_query:
        semantic_matches = get_relevant_messages(
            session_id=session_id,
            prompt=semantic_query,
            top_k=semantic_top_k,
            fall_back=True,
        )

    return {
        "session_id": session_id,
        "message_count": get_message_count(session_id),
        "turn_count": get_turn_count(session_id),
        "summary": summary,
        "summary_meta": summary_meta,
        "recent_messages": recent_messages,
        "semantic_matches": semantic_matches,
        "last_tool_result": last_tool_result,
        "meta": meta,
        "redis_present": bool(
            recent_messages or summary or last_tool_result or meta or summary_meta
        ),
    }
