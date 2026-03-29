from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class CacheEntry:
    value: Any
    created_at: int
    expires_at: Optional[int]
    source_version: int


@dataclass
class CacheStats:
    requests: int = 0
    hits: int = 0
    misses: int = 0
    expired_entries: int = 0
    expiry_misses: int = 0
    stale_serves: int = 0
    writes: int = 0
    total_hit_age: int = 0

    def as_dict(self) -> Dict[str, float]:
        hit_rate = self.hits / self.requests if self.requests else 0.0
        avg_item_age_at_hit = self.total_hit_age / self.hits if self.hits else 0.0
        return {
            "requests": self.requests,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": round(hit_rate, 4),
            "expired_entries": self.expired_entries,
            "expiry_misses": self.expiry_misses,
            "stale_serves": self.stale_serves,
            "writes": self.writes,
            "avg_item_age_at_hit": round(avg_item_age_at_hit, 2),
        }


class TTLCache:
    def __init__(self, default_ttl_seconds: Optional[int]):
        self.default_ttl_seconds = default_ttl_seconds
        self.data: Dict[str, CacheEntry] = {}
        self.stats = CacheStats()

    def _is_expired(self, entry: CacheEntry, now_ts: int) -> bool:
        if entry.expires_at is None:
            return False
        return now_ts >= entry.expires_at

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

        if self._is_expired(entry, now_ts):
            del self.data[key]
            self.stats.misses += 1
            self.stats.expired_entries += 1
            self.stats.expiry_misses += 1
            return None

        self.stats.hits += 1
        self.stats.total_hit_age += now_ts - entry.created_at

        # stale serve = cache hit, but underlying source version has changed
        if (
            expected_source_version is not None
            and entry.source_version != expected_source_version
        ):
            self.stats.stale_serves += 1

        return entry.value

    def put(
        self,
        key: str,
        value: Any,
        now_ts: int,
        source_version: int,
        ttl_seconds: Optional[int] = None,
    ) -> None:
        ttl = self.default_ttl_seconds if ttl_seconds is None else ttl_seconds
        expires_at = None if ttl is None else now_ts + ttl

        self.data[key] = CacheEntry(
            value=value,
            created_at=now_ts,
            expires_at=expires_at,
            source_version=source_version,
        )
        self.stats.writes += 1


@dataclass
class Operation:
    ts: int
    key: str
    source_version: int


@dataclass
class BenchmarkResult:
    scenario_name: str
    ttl_seconds: Optional[int]
    stats: Dict[str, float]


def run_ttl_benchmark(
    scenario_name: str,
    operations: List[Operation],
    ttl_seconds: Optional[int],
) -> BenchmarkResult:
    cache = TTLCache(default_ttl_seconds=ttl_seconds)

    for op in operations:
        cached = cache.get(
            key=op.key,
            now_ts=op.ts,
            expected_source_version=op.source_version,
        )
        if cached is None:
            fresh_value = f"value:{op.key}:v{op.source_version}"
            cache.put(
                key=op.key,
                value=fresh_value,
                now_ts=op.ts,
                source_version=op.source_version,
            )

    return BenchmarkResult(
        scenario_name=scenario_name,
        ttl_seconds=ttl_seconds,
        stats=cache.stats.as_dict(),
    )


# -------------------------------------------------------------------
# Scenario builders
# -------------------------------------------------------------------

def scenario_repeats_just_after_expiry() -> List[Operation]:
    """
    Same item repeats often enough that a short TTL will create many expiry misses.
    Underlying source is stable.
    """
    return [
        Operation(ts=0, key="weather:malta", source_version=1),
        Operation(ts=30, key="weather:malta", source_version=1),
        Operation(ts=61, key="weather:malta", source_version=1),
        Operation(ts=90, key="weather:malta", source_version=1),
        Operation(ts=121, key="weather:malta", source_version=1),
        Operation(ts=150, key="weather:malta", source_version=1),
        Operation(ts=181, key="weather:malta", source_version=1),
    ]


def scenario_source_changes_but_ttl_is_long() -> List[Operation]:
    """
    Same key is reused while underlying source changes over time.
    Long TTL will increase stale serves.
    """
    return [
        Operation(ts=0, key="stock:ABC", source_version=1),
        Operation(ts=20, key="stock:ABC", source_version=1),
        Operation(ts=40, key="stock:ABC", source_version=2),   # source changed
        Operation(ts=50, key="stock:ABC", source_version=2),
        Operation(ts=70, key="stock:ABC", source_version=3),   # source changed again
        Operation(ts=80, key="stock:ABC", source_version=3),
        Operation(ts=130, key="stock:ABC", source_version=4),  # much later
    ]


def scenario_stable_vs_unstable_mix() -> List[Operation]:
    """
    Mixed workload:
    - session memory: stable enough
    - stock/news/tool result: changes more often
    """
    return [
        Operation(ts=0, key="session:user:42", source_version=1),
        Operation(ts=5, key="news:ai", source_version=1),
        Operation(ts=10, key="session:user:42", source_version=1),
        Operation(ts=20, key="tool:search:q=redis", source_version=1),
        Operation(ts=25, key="news:ai", source_version=2),
        Operation(ts=30, key="session:user:42", source_version=1),
        Operation(ts=40, key="tool:search:q=redis", source_version=1),
        Operation(ts=50, key="news:ai", source_version=3),
        Operation(ts=55, key="session:user:42", source_version=1),
        Operation(ts=80, key="tool:search:q=redis", source_version=2),
        Operation(ts=100, key="session:user:42", source_version=1),
        Operation(ts=110, key="news:ai", source_version=4),
    ]


# -------------------------------------------------------------------
# Reporting
# -------------------------------------------------------------------

def print_results(results: List[BenchmarkResult]) -> None:
    headers = [
        "scenario",
        "ttl",
        "requests",
        "hits",
        "misses",
        "hit_rate",
        "expired_entries",
        "expiry_misses",
        "stale_serves",
        "writes",
        "avg_item_age_at_hit",
    ]

    rows: List[List[Any]] = []
    for r in results:
        s = r.stats
        rows.append([
            r.scenario_name,
            r.ttl_seconds,
            s["requests"],
            s["hits"],
            s["misses"],
            s["hit_rate"],
            s["expired_entries"],
            s["expiry_misses"],
            s["stale_serves"],
            s["writes"],
            s["avg_item_age_at_hit"],
        ])

    widths = []
    for i, h in enumerate(headers):
        max_len = len(str(h))
        for row in rows:
            max_len = max(max_len, len(str(row[i])))
        widths.append(max_len)

    def fmt_row(row: List[Any]) -> str:
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(row))

    print(fmt_row(headers))
    print("-+-".join("-" * w for w in widths))
    for row in rows:
        print(fmt_row(row))


def main() -> None:
    ttl_values = [30, 60, 300]

    scenarios: List[Tuple[str, List[Operation]]] = [
        ("repeats_just_after_expiry", scenario_repeats_just_after_expiry()),
        ("source_changes_but_ttl_long", scenario_source_changes_but_ttl_is_long()),
        ("stable_vs_unstable_mix", scenario_stable_vs_unstable_mix()),
    ]

    results: List[BenchmarkResult] = []
    for scenario_name, ops in scenarios:
        for ttl in ttl_values:
            results.append(run_ttl_benchmark(scenario_name, ops, ttl))

    print_results(results)


if __name__ == "__main__":
    main()