from __future__ import annotations

import csv
import time
from typing import Any, Dict, List

import httpx

API_URL = "http://127.0.0.1:8001/chat"
OUTPUT_CSV = "benchmark_results.csv"

TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "short_no_retrieval",
        "message": "What is a context window?",
        "use_retrieval": False,
    },
    {
        "label": "short_with_retrieval",
        "message": "Explain static prefix vs dynamic suffix in prompts",
        "use_retrieval": True,
    },
    {
        "label": "retrieval_caching_topic",
        "message": "Why does prompt structure matter for caching?",
        "use_retrieval": True,
    },
    {
        "label": "retrieval_local_model",
        "message": "How does Ollama help with local LLM testing?",
        "use_retrieval": True,
    },
    {
        "label": "repeat_same_1",
        "message": "Explain static prefix vs dynamic suffix in prompts",
        "use_retrieval": True,
    },
    {
        "label": "repeat_same_2",
        "message": "Explain static prefix vs dynamic suffix in prompts",
        "use_retrieval": True,
    },
]


def run_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    started = time.perf_counter()

    response = client.post(
        API_URL,
        json={
            "message": case["message"],
            "use_retrieval": case["use_retrieval"],
        },
        timeout=180.0,
    )

    wall_ms = (time.perf_counter() - started) * 1000

    response.raise_for_status()
    data = response.json()

    prompt_stats = data.get("prompt_stats", {})
    timings = data.get("timings", {})

    return {
        "label": case["label"],
        "message": case["message"],
        "use_retrieval": case["use_retrieval"],
        "request_wall_ms": round(wall_ms, 2),
        "retrieval_ms": timings.get("retrieval_ms"),
        "prompt_assembly_ms": timings.get("prompt_assembly_ms"),
        "ttft_ms": timings.get("ttft_ms"),
        "model_total_ms": timings.get("model_total_ms"),
        "total_ms": timings.get("total_ms"),
        "total_tokens": prompt_stats.get("total_tokens"),
        "system_tokens": prompt_stats.get("system_tokens"),
        "context_tokens": prompt_stats.get("context_tokens"),
        "user_tokens": prompt_stats.get("user_tokens"),
        "tokenizer_name": prompt_stats.get("tokenizer_name"),
        "count_method": prompt_stats.get("count_method"),
        "has_retrieval_context": prompt_stats.get("has_retrieval_context"),
        "answer_preview": (data.get("answer") or "")[:160].replace("\n", " "),
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        for idx, case in enumerate(TEST_CASES, start=1):
            print(f"[{idx}/{len(TEST_CASES)}] Running: {case['label']}")
            try:
                row = run_case(client, case)
                rows.append(row)
                print(
                    f"  ok | ttft={row['ttft_ms']} ms | total={row['total_ms']} ms | tokens={row['total_tokens']}"
                )
            except Exception as exc:
                print(f"  failed | {case['label']} | {exc}")

    if not rows:
        print("No benchmark rows collected.")
        return

    fieldnames = list(rows[0].keys())
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()