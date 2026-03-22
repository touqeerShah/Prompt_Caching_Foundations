from __future__ import annotations

import csv
from typing import Any, Dict, List

import httpx

from prompt_lab import prefix_similarity_ratio

API_URL = "http://127.0.0.1:8001/chat"
OUTPUT_CSV = "prompt_version_benchmark.csv"

TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "a_first",
        "prompt_version": "a",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "a_repeat",
        "prompt_version": "a",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "b_first",
        "prompt_version": "b",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "b_repeat",
        "prompt_version": "b",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "c_first",
        "prompt_version": "c",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "c_repeat",
        "prompt_version": "c",
        "message": "Explain why stable prompt prefixes improve token reuse.",
        "use_retrieval": True,
    },
    {
        "label": "c_changed_suffix",
        "prompt_version": "c",
        "message": "Why does putting the user message at the end help caching?",
        "use_retrieval": True,
    },
]


def run_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(
        API_URL,
        json={
            "message": case["message"],
            "use_retrieval": case["use_retrieval"],
            "prompt_version": case["prompt_version"],
            "user_id": "user-123",
            "tenant_id": "tenant-001",
        },
        timeout=180.0,
    )
    response.raise_for_status()
    data = response.json()

    prompt_stats = data["prompt_stats"]
    timings = data["timings"]

    return {
        "label": case["label"],
        "prompt_version": case["prompt_version"],
        "message": case["message"],
        "full_prompt_sha256": prompt_stats["full_prompt_sha256"],
        "static_prefix_sha256": prompt_stats["static_prefix_sha256"],
        "full_prompt_chars": prompt_stats["full_prompt_chars"],
        "static_prefix_chars": prompt_stats["static_prefix_chars"],
        "total_tokens": prompt_stats["total_tokens"],
        "static_prefix_tokens": prompt_stats["static_prefix_tokens"],
        "ttft_ms": timings["ttft_ms"],
        "model_total_ms": timings["model_total_ms"],
        "total_ms": timings["total_ms"],
        "prompt_preview": data["prompt_preview"],
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        for case in TEST_CASES:
            print(f"Running {case['label']} ...")
            row = run_case(client, case)
            rows.append(row)

    # add pairwise prefix similarity to previous row for easier learning
    for i in range(1, len(rows)):
        prev = rows[i - 1]
        curr = rows[i]
        curr["prefix_similarity_vs_prev"] = prefix_similarity_ratio(
            prev["prompt_preview"],
            curr["prompt_preview"],
        )

    if rows:
        rows[0]["prefix_similarity_vs_prev"] = None

    fieldnames = list(rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
