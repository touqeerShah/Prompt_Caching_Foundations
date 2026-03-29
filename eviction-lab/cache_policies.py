from __future__ import annotations

from typing import Any, Dict, Optional


CacheDict = Dict[str, Dict[str, Any]]


def is_expired(entry: Dict[str, Any], now_ts: int) -> bool:
    expires_at = entry.get("expires_at")
    if expires_at is None:
        return False
    return now_ts >= expires_at


def select_lru(cache: CacheDict) -> Optional[str]:
    if not cache:
        return None

    return min(
        cache.items(),
        key=lambda kv: (kv[1]["last_access_at"], kv[1]["created_at"]),
    )[0]


def select_lfu(cache: CacheDict) -> Optional[str]:
    if not cache:
        return None

    return min(
        cache.items(),
        key=lambda kv: (
            kv[1]["access_count"],
            kv[1]["last_access_at"],
            kv[1]["created_at"],
        ),
    )[0]


def select_fifo(cache: CacheDict) -> Optional[str]:
    if not cache:
        return None

    return min(
        cache.items(),
        key=lambda kv: kv[1]["created_at"],
    )[0]


def resolve_ttl(key: str) -> int:
    if key.startswith("session:"):
        return 300
    if key.startswith("tool:"):
        return 120
    if key.startswith("news:"):
        return 60
    if key.startswith("stock:"):
        return 20
    return 60