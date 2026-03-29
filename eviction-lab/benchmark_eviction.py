from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from cache_policies import select_lru, select_lfu, select_fifo, resolve_ttl
from cache_store import CacheStore, PROTECTED_SHARED_KEYS
from scenarios import (
    Operation,
    scenario_active_chat_recency,
    scenario_shared_template_popularity,
    scenario_long_tail_vs_shared_assets,
    scenario_stable_vs_unstable_ttl_classes,
    scenario_fifo_bad_case,
)


def run_scenario(
    scenario_name: str,
    ops: List[Operation],
    max_entries: int,
    ttl_mode_name: str,
    ttl_resolver: Callable[[str], int],
    policy_name: str,
    eviction_selector,
) -> Dict[str, object]:
    cache = CacheStore(
        max_entries=max_entries,
        eviction_selector=eviction_selector,
        ttl_resolver=ttl_resolver,
        protected_shared_keys=PROTECTED_SHARED_KEYS,
    )

    for op in ops:
        value = cache.get(
            key=op.key,
            now_ts=op.ts,
            expected_source_version=op.source_version,
        )
        if value is None:
            cache.put(
                key=op.key,
                value=f"value:{op.key}:v{op.source_version}",
                now_ts=op.ts,
                source_version=op.source_version,
            )

    surviving = cache.surviving_keys()
    shared_survivors = len(surviving.intersection(PROTECTED_SHARED_KEYS))
    shared_total = len(PROTECTED_SHARED_KEYS)
    shared_survival_rate = shared_survivors / shared_total if shared_total else 0.0

    result = {
        "scenario": scenario_name,
        "policy": policy_name,
        "ttl_mode": ttl_mode_name,
        "max_entries": max_entries,
        "shared_survivors": shared_survivors,
        "shared_survival_rate": round(shared_survival_rate, 4),
    }
    result.update(cache.stats.summary())
    return result


def fixed_ttl_resolver(seconds: int) -> Callable[[str], int]:
    def _resolver(_: str) -> int:
        return seconds
    return _resolver


def print_table(rows: List[Dict[str, object]]) -> None:
    columns = [
        "scenario",
        "policy",
        "ttl_mode",
        "max_entries",
        "requests",
        "hits",
        "misses",
        "hit_rate",
        "evictions",
        "expired_entries",
        "expiry_misses",
        "stale_serves",
        "hot_item_evictions",
        "shared_key_evictions",
        "shared_survivors",
        "shared_survival_rate",
        "avg_item_age_at_hit",
        "avg_age_of_evicted_entries",
        "avg_access_count_of_evicted_entries",
    ]

    widths = {
        col: max(len(col), max(len(str(row.get(col, ""))) for row in rows))
        for col in columns
    }

    header = " | ".join(col.ljust(widths[col]) for col in columns)
    sep = "-+-".join("-" * widths[col] for col in columns)
    print(header)
    print(sep)

    for row in rows:
        print(" | ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def main() -> None:
    scenarios: List[Tuple[str, List[Operation]]] = [
        ("active_chat_recency", scenario_active_chat_recency()),
        ("shared_template_popularity", scenario_shared_template_popularity()),
        ("long_tail_vs_shared_assets", scenario_long_tail_vs_shared_assets()),
        ("stable_vs_unstable_ttl_classes", scenario_stable_vs_unstable_ttl_classes()),
        ("fifo_bad_case", scenario_fifo_bad_case()),
    ]

    ttl_modes = [
        ("fixed_60s", fixed_ttl_resolver(60)),
        ("per_key_ttl", resolve_ttl),
    ]

    policies = [
        ("TTL+LRU", select_lru),
        ("TTL+LFU", select_lfu),
        ("TTL+FIFO", select_fifo),
    ]

    results: List[Dict[str, object]] = []
    for scenario_name, ops in scenarios:
        for ttl_mode_name, ttl_resolver_fn in ttl_modes:
            for policy_name, selector in policies:
                results.append(
                    run_scenario(
                        scenario_name=scenario_name,
                        ops=ops,
                        max_entries=4,
                        ttl_mode_name=ttl_mode_name,
                        ttl_resolver=ttl_resolver_fn,
                        policy_name=policy_name,
                        eviction_selector=selector,
                    )
                )

    print_table(results)


if __name__ == "__main__":
    main()