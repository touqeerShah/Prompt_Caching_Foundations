from __future__ import annotations

import csv
from typing import Any, Dict, List

import httpx

API_URL = "http://127.0.0.1:8001/chat"
OUTPUT_CSV = "exact_cache_results.csv"

TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "first_request",
        "message": "Explain why stable prefixes help caching.",
        "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
        "use_cache": True,
    },
    {
        "label": "repeat_same_request",
        "message": "Explain why stable prefixes help caching.",
        "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
        "use_cache": True,
    },
    {
        "label": "different_suffix",
        "message": "Why does changing only the suffix preserve reuse better?",
        "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
        "use_cache": True,
    },
    {
        "label": "cache_disabled",
        "message": "Explain why stable prefixes help caching.",
        "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
        "use_cache": False,
    },
]


def run_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(API_URL, json=case, timeout=180.0)
    response.raise_for_status()
    data = response.json()

    return {
        "label": case["label"],
        "message": case["message"],
        "use_cache": case["use_cache"],
        "cache_hit": data["cache"]["hit"],
        "prompt_tokens": data["prompt_stats"]["estimated_prompt_tokens"],
        "prompt_chars": data["prompt_stats"]["prompt_chars"],
        "prompt_assembly_ms": data["timings"]["prompt_assembly_ms"],
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
                f"  hit={row['cache_hit']} | total={row['total_ms']} ms | model={row['model_ms']} ms"
            )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()