from __future__ import annotations

import csv
from typing import Any, Dict, List

import httpx

API_URL = "http://127.0.0.1:8001/chat"
OUTPUT_CSV = "semantic_cache_results.csv"

TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "seed_password_reset",
        "message": "How do I reset my password?",
        "tenant_id": "tenant-001",
        "language": "en",
        "version": "v1",
        "category": "faq",
        "use_semantic_cache": True,
    },
    {
        "label": "similar_password_reset",
        "message": "I forgot my password, what should I do?",
        "tenant_id": "tenant-001",
        "language": "en",
        "version": "v1",
        "category": "faq",
        "use_semantic_cache": True,
    },
    {
        "label": "similar_password_reset_strict",
        "message": "I forgot my password, what should I do?",
        "tenant_id": "tenant-001",
        "language": "en",
        "version": "v1",
        "category": "faq",
        "use_semantic_cache": True,
        "distance_threshold": 0.08,
    },
    {
        "label": "tenant_isolation_test",
        "message": "I forgot my password, what should I do?",
        "tenant_id": "tenant-999",
        "language": "en",
        "version": "v1",
        "category": "faq",
        "use_semantic_cache": True,
    },
    {
        "label": "exact_repeat",
        "message": "How do I reset my password?",
        "tenant_id": "tenant-001",
        "language": "en",
        "version": "v1",
        "category": "faq",
        "use_semantic_cache": True,
    },
]


def run_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(API_URL, json=case, timeout=180.0)
    response.raise_for_status()
    data = response.json()

    return {
        "label": case["label"],
        "message": case["message"],
        "tenant_id": case["tenant_id"],
        "semantic_cache_hit": data["semantic_cache"]["hit"],
        "distance": data["semantic_cache"]["distance"],
        "prompt_tokens": data["prompt_stats"]["estimated_prompt_tokens"],
        "cache_lookup_ms": data["timings"]["cache_lookup_ms"],
        "model_ms": data["timings"]["model_ms"],
        "cache_write_ms": data["timings"]["cache_write_ms"],
        "total_ms": data["timings"]["total_ms"],
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        for idx, case in enumerate(TEST_CASES, start=1):
            print(f"[{idx}/{len(TEST_CASES)}] {case['label']}")
            row = run_case(client, case)
            rows.append(row)
            print(
                f"  hit={row['semantic_cache_hit']} | distance={row['distance']} | total={row['total_ms']} ms"
            )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()