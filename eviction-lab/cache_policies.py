from __future__ import annotations

from typing import Any, Dict, Optional

from vector_utils import average_similarity


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

    return min(cache.items(), key=lambda kv: kv[1]["created_at"])[0]


def select_semantic_redundant(cache: CacheDict) -> Optional[str]:
    if not cache:
        return None

    items = [(k, v) for k, v in cache.items() if v.get("semantic_vector") is not None]
    if len(items) <= 1:
        return select_fifo(cache)

    scored = []
    for key, entry in items:
        target = entry["semantic_vector"]
        others = [
            other_entry["semantic_vector"]
            for other_key, other_entry in items
            if other_key != key
        ]
        redundancy_score = average_similarity(target, others)

        scored.append(
            (
                key,
                redundancy_score,
                entry["created_at"],
            )
        )

    # Evict highest redundancy score.
    # If tied, evict older inserted item first.
    scored.sort(key=lambda x: (-x[1], x[2]))
    return scored[0][0]


def resolve_ttl(key: str) -> int:
    if key.startswith("session:"):
        return 300
    if key.startswith("tool:"):
        return 120
    if key.startswith("news:"):
        return 60
    if key.startswith("stock:"):
        return 20
    if key.startswith("rag:"):
        return 300
    return 60