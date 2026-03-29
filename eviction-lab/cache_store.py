from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any, Callable, Dict, Optional, Set

from cache_policies import is_expired, resolve_ttl


PROTECTED_SHARED_KEYS: Set[str] = {
    "tool:template:system",
    "tool:policy:security",
    "tool:schema:extract",
}


@dataclass
class CacheStats:
    requests: int = 0
    hits: int = 0
    misses: int = 0
    writes: int = 0

    evictions: int = 0
    expired_entries: int = 0
    expiry_misses: int = 0
    stale_serves: int = 0
    hot_item_evictions: int = 0
    shared_key_evictions: int = 0

    total_hit_age: int = 0
    total_evicted_age: int = 0
    total_evicted_access_count: int = 0

    def summary(self) -> Dict[str, float]:
        hit_rate = self.hits / self.requests if self.requests else 0.0
        avg_item_age_at_hit = self.total_hit_age / self.hits if self.hits else 0.0
        avg_age_of_evicted_entries = (
            self.total_evicted_age / self.evictions if self.evictions else 0.0
        )
        avg_access_count_of_evicted_entries = (
            self.total_evicted_access_count / self.evictions if self.evictions else 0.0
        )

        out = asdict(self)
        out["hit_rate"] = round(hit_rate, 4)
        out["avg_item_age_at_hit"] = round(avg_item_age_at_hit, 2)
        out["avg_age_of_evicted_entries"] = round(avg_age_of_evicted_entries, 2)
        out["avg_access_count_of_evicted_entries"] = round(
            avg_access_count_of_evicted_entries, 2
        )
        return out


class CacheStore:
    def __init__(
        self,
        max_entries: int,
        eviction_selector: Callable[[Dict[str, Dict[str, Any]]], Optional[str]],
        ttl_resolver: Callable[[str], int] = resolve_ttl,
        hot_threshold: int = 3,
        protected_shared_keys: Optional[Set[str]] = None,
    ):
        self.max_entries = max_entries
        self.eviction_selector = eviction_selector
        self.ttl_resolver = ttl_resolver
        self.hot_threshold = hot_threshold
        self.protected_shared_keys = protected_shared_keys or set()

        self.data: Dict[str, Dict[str, Any]] = {}
        self.stats = CacheStats()

    def _purge_expired(self, now_ts: int) -> None:
        expired_keys = [
            key for key, entry in self.data.items() if is_expired(entry, now_ts)
        ]
        for key in expired_keys:
            del self.data[key]
            self.stats.expired_entries += 1

    def _evict_one(self, now_ts: int) -> None:
        key = self.eviction_selector(self.data)
        if key is None:
            return

        entry = self.data[key]
        age = now_ts - entry["created_at"]

        self.stats.evictions += 1
        self.stats.total_evicted_age += age
        self.stats.total_evicted_access_count += entry["access_count"]

        if entry["access_count"] >= self.hot_threshold:
            self.stats.hot_item_evictions += 1

        if key in self.protected_shared_keys:
            self.stats.shared_key_evictions += 1

        del self.data[key]

    def _evict_if_needed(self, now_ts: int) -> None:
        self._purge_expired(now_ts)
        while len(self.data) > self.max_entries:
            self._evict_one(now_ts)

    def get(
        self,
        key: str,
        now_ts: int,
        expected_source_version: Optional[int] = None,
    ) -> Optional[Any]:
        self.stats.requests += 1

        entry = self.data.get(key)
        if entry is None:
            self.stats.misses += 1
            return None

        if is_expired(entry, now_ts):
            del self.data[key]
            self.stats.misses += 1
            self.stats.expired_entries += 1
            self.stats.expiry_misses += 1
            return None

        entry["last_access_at"] = now_ts
        entry["access_count"] += 1

        self.stats.hits += 1
        self.stats.total_hit_age += now_ts - entry["created_at"]

        if (
            expected_source_version is not None
            and entry["source_version"] != expected_source_version
        ):
            self.stats.stale_serves += 1

        return entry["value"]

    def put(
        self,
        key: str,
        value: Any,
        now_ts: int,
        source_version: int,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        ttl = self.ttl_resolver(key) if ttl_seconds is None else ttl_seconds
        expires_at = now_ts + ttl if ttl is not None else None

        existing = self.data.get(key)

        self.data[key] = {
            "key": key,
            "value": value,
            "created_at": existing["created_at"] if existing else now_ts,
            "last_access_at": now_ts,
            "access_count": (existing["access_count"] if existing else 0) + 1,
            "ttl_seconds": ttl,
            "expires_at": expires_at,
            "source_version": source_version,
        }

        self.stats.writes += 1
        self._evict_if_needed(now_ts)

    def snapshot(self) -> Dict[str, Dict[str, Any]]:
        return self.data.copy()

    def surviving_keys(self) -> Set[str]:
        return set(self.data.keys())