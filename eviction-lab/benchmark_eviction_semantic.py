from __future__ import annotations

from typing import Callable, Dict, List, Tuple

from cache_policies import (
    select_lru,
    select_lfu,
    select_fifo,
    select_semantic_redundant,
    resolve_ttl,
)
from cache_store import CacheStore, PROTECTED_SHARED_KEYS
from scenarios_semantic import (
    Operation,
    scenario_semantic_duplicates,
    scenario_semantic_memory_flood,
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
                semantic_vector=op.semantic_vector,
            )

    result = {
        "scenario": scenario_name,
        "policy": policy_name,
        "ttl_mode": ttl_mode_name,
        "max_entries": max_entries,
        "retained_diversity_score": cache.retained_diversity_score(),
    }
    result.update(cache.stats.summary())
    return result


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
        "semantic_evictions",
        "avg_evicted_redundancy_score",
        "retained_diversity_score",
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
        ("semantic_duplicates", scenario_semantic_duplicates()),
        ("semantic_memory_flood", scenario_semantic_memory_flood()),
    ]

    policies = [
        ("TTL+LRU", select_lru),
        ("TTL+LFU", select_lfu),
        ("TTL+FIFO", select_fifo),
        ("TTL+Semantic", select_semantic_redundant),
    ]

    results: List[Dict[str, object]] = []
    for scenario_name, ops in scenarios:
        for policy_name, selector in policies:
            results.append(
                run_scenario(
                    scenario_name=scenario_name,
                    ops=ops,
                    max_entries=4,
                    ttl_mode_name="per_key_ttl",
                    ttl_resolver=resolve_ttl,
                    policy_name=policy_name,
                    eviction_selector=selector,
                )
            )

    print_table(results)


if __name__ == "__main__":
    main()