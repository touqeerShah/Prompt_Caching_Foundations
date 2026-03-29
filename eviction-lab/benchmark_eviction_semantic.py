from __future__ import annotations

from functools import partial
from typing import Callable, Dict, List, Tuple

from cache_policies import (
    select_lru,
    select_lfu,
    select_semantic_redundant,
    select_hybrid_semantic_recency,
    select_hybrid_semantic_frequency,
    resolve_ttl,
)
from cache_store import CacheStore
from scenarios_semantic import Operation, scenario_semantic_reuse_pressure


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
    )

    for op in ops:
        if op.op_type == "write":
            cache.put(
                key=op.key,
                value=f"value:{op.key}:v{op.source_version}",
                now_ts=op.ts,
                source_version=op.source_version,
                semantic_vector=op.semantic_vector,
            )
        elif op.op_type == "read":
            cache.get(
                key=op.key,
                now_ts=op.ts,
                expected_source_version=op.source_version,
            )
        else:
            raise ValueError(f"Unknown op_type: {op.op_type}")

    result = {
        "scenario": scenario_name,
        "policy": policy_name,
        "ttl_mode": ttl_mode_name,
        "max_entries": max_entries,
        "retained_diversity_score": cache.retained_diversity_score(),
        "surviving_keys": sorted(cache.surviving_keys()),
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

    print("\nRetained keys by policy:")
    for row in rows:
        print(f"{row['policy']}: {row['surviving_keys']}")


def main() -> None:
    scenarios: List[Tuple[str, List[Operation]]] = [
        ("semantic_reuse_pressure", scenario_semantic_reuse_pressure()),
    ]

    policies = [
        ("TTL+Semantic", select_semantic_redundant),
        ("TTL+LRU", select_lru),
        ("TTL+LFU", select_lfu),
        (
            "TTL+Hybrid-SR",
            partial(
                select_hybrid_semantic_recency,
                redundancy_weight=1.0,
                recency_weight=0.6,
            ),
        ),
        (
            "TTL+Hybrid-SF",
            partial(
                select_hybrid_semantic_frequency,
                redundancy_weight=1.0,
                frequency_weight=0.6,
            ),
        ),
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