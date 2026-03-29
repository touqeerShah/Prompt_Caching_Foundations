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


def _redundancy_scores(cache: CacheDict) -> Dict[str, float]:
    items = [(k, v) for k, v in cache.items() if v.get("semantic_vector") is not None]
    if not items:
        return {}

    scores: Dict[str, float] = {}
    for key, entry in items:
        target = entry["semantic_vector"]
        others = [
            other_entry["semantic_vector"]
            for other_key, other_entry in items
            if other_key != key
        ]
        scores[key] = average_similarity(target, others) if others else 0.0

    return scores


def _normalize_field(cache: CacheDict, field: str) -> Dict[str, float]:
    if not cache:
        return {}

    values = {k: float(v.get(field, 0)) for k, v in cache.items()}
    min_v = min(values.values())
    max_v = max(values.values())

    if max_v == min_v:
        return {k: 0.0 for k in values}

    return {
        k: (val - min_v) / (max_v - min_v)
        for k, val in values.items()
    }


def select_semantic_redundant(cache: CacheDict) -> Optional[str]:
    if not cache:
        return None

    redundancy = _redundancy_scores(cache)
    if not redundancy:
        return select_fifo(cache)

    return max(
        redundancy.items(),
        key=lambda kv: (kv[1], -cache[kv[0]]["created_at"]),
    )[0]


def select_hybrid_semantic_recency(
    cache: CacheDict,
    redundancy_weight: float = 1.0,
    recency_weight: float = 0.5,
) -> Optional[str]:
    if not cache:
        return None

    redundancy = _redundancy_scores(cache)
    if not redundancy:
        return select_lru(cache)

    recency = _normalize_field(cache, "last_access_at")

    scored = []
    for key in cache.keys():
        r = redundancy.get(key, 0.0)
        rec = recency.get(key, 0.0)
        eviction_score = redundancy_weight * r - recency_weight * rec
        scored.append((key, eviction_score, cache[key]["created_at"]))

    scored.sort(key=lambda x: (-x[1], x[2]))
    return scored[0][0]


def select_hybrid_semantic_frequency(
    cache: CacheDict,
    redundancy_weight: float = 1.0,
    frequency_weight: float = 0.5,
) -> Optional[str]:
    if not cache:
        return None

    redundancy = _redundancy_scores(cache)
    if not redundancy:
        return select_lfu(cache)

    frequency = _normalize_field(cache, "access_count")

    scored = []
    for key in cache.keys():
        r = redundancy.get(key, 0.0)
        freq = frequency.get(key, 0.0)
        eviction_score = redundancy_weight * r - frequency_weight * freq
        scored.append((key, eviction_score, cache[key]["created_at"]))

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