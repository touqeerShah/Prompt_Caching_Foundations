from __future__ import annotations

import csv
from typing import Any, Dict, List

import httpx

BASE_URL = "http://127.0.0.1:8001"
CHAT_URL = f"{BASE_URL}/chat"
OUTPUT_CSV = "recovery_benchmark_results.csv"

CASES: List[Dict[str, Any]] = [
    {
        "label": "hot_fast_path",
        "payload": {
            "session_id": "sess-recovery-001",
            "message": "We use Redis as hot memory and Postgres as durable fallback."
        },
    },
    {
        "label": "follow_up_fast_path",
        "payload": {
            "session_id": "sess-recovery-001",
            "message": "What do we use for durable fallback?"
        },
    },
    {
        "label": "force_pg_restore",
        "payload": {
            "session_id": "sess-recovery-001",
            "message": "What did we decide about durable fallback?",
            "force_pg_restore": True
        },
    },
]


def run_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(CHAT_URL, json=case["payload"], timeout=240.0)
    response.raise_for_status()
    data = response.json()

    return {
        "label": case["label"],
        "mode": data["memory"]["mode"],
        "restored_from_pg": data["memory"]["restored_from_pg"],
        "degraded_reason": data["memory"]["degraded_reason"],
        "recent_count": data["memory"]["recent_count"],
        "relevant_count": data["memory"]["relevant_count"],
        "recovery_ms": data["timings"].get("recovery_ms"),
        "redis_hot_ms": data["timings"].get("redis_hot_ms"),
        "pg_restore_ms": data["timings"].get("pg_restore_ms"),
        "semantic_ms": data["timings"].get("semantic_ms"),
        "model_ms": data["timings"].get("model_ms"),
        "summary_update_ms": data["timings"].get("summary_update_ms"),
        "total_ms": data["timings"].get("total_ms"),
        "answer_preview": data["answer"][:120].replace("\n", " "),
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        for i, case in enumerate(CASES, start=1):
            print(f"[{i}/{len(CASES)}] {case['label']}")
            row = run_case(client, case)
            rows.append(row)
            print(
                f"  mode={row['mode']} | recovery={row['recovery_ms']} ms | total={row['total_ms']} ms"
            )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()