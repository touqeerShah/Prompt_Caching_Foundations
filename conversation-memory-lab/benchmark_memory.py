from __future__ import annotations

import csv
from typing import Any, Dict, List
from unittest import case

import httpx

BASE_URL = "http://127.0.0.1:8001"
CHAT_URL = f"{BASE_URL}/chat"
OUTPUT_CSV = "memory_benchmark_results.csv"


CHAT_CASES: List[Dict[str, Any]] = [
    {
        "label": "seed_session",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "We decided to use Redis for hot session memory and Postgres for durable storage.",
        },
    },
    {
        "label": "follow_up_question_1",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "What are we using for durable storage?",
        },
    },
    {
        "label": "follow_up_question_2",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "Why are we keeping Redis in front of Postgres?",
        },
    },
    {
        "label": "follow_up_question_3",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "Summarize our storage decision.",
        },
    },
    {
        "label": "tool_result_turn",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "Store the last query result.",
            "tool_result": {
                "tool": "db_lookup",
                "result": {
                    "db": "postgres",
                    "purpose": "durable storage"
                }
            }
        },
    },
    {
        "label": "force_pg_restore_turn",
        "payload": {
            "session_id": "sess-bench-001",
            "message": "What did we discuss earlier about durable storage?",
            "force_pg_restore": True,
        },
    },
]

def run_chat_case(client: httpx.Client, case: Dict[str, Any]) -> Dict[str, Any]:
    response = client.post(CHAT_URL, json=case["payload"], timeout=240.0)
    response.raise_for_status()
    data = response.json()

    return {
        "label": case["label"],
        "type": "chat",
        "session_id": data["session_id"],
        "restored_from_pg": data["memory"]["restored_from_pg"],
        "recent_count": data["memory"]["recent_count"],
        "relevant_count": data["memory"]["relevant_count"],
        "has_summary": data["memory"]["has_summary"],
        "has_tool_result": data["memory"]["has_tool_result"],
        "recent_ms": data["timings"]["recent_ms"],
        "semantic_ms": data["timings"]["semantic_ms"],
        "prompt_ms": data["timings"]["prompt_ms"],
        "model_ms": data["timings"]["model_ms"],
        "summary_update_ms": data["timings"]["summary_update_ms"],
        "write_ms": data["timings"]["write_ms"],
        "total_ms": data["timings"]["total_ms"],
        "answer_preview": data["answer"][:140].replace("\n", " "),
    }


def run_debug_case(
    client: httpx.Client,
    session_id: str,
    semantic_query: str | None = None,
    force_pg_restore: bool = False,
) -> Dict[str, Any]:
    response = client.get(
        f"{BASE_URL}/session/{session_id}",
        params={
            "semantic_query": semantic_query,
            "force_pg_restore": str(force_pg_restore).lower(),
        },
        timeout=120.0,
    )
    response.raise_for_status()
    data = response.json()
    return {
        "label": case["label"],
        "type": "chat",
        "session_id": data["session_id"],
        "restored_from_pg": data["memory"]["restored_from_pg"],
        "recent_count": data["memory"]["recent_count"],
        "relevant_count": data["memory"]["relevant_count"],
        "has_summary": data["memory"]["has_summary"],
        "has_tool_result": data["memory"]["has_tool_result"],
        "turn_count": data["memory"]["turn_count"],
        "summary_updated": data["memory"]["summary_updated"],
        "summary_reason": data["memory"]["summary_reason"],
        "recent_ms": data["timings"]["recent_ms"],
        "semantic_ms": data["timings"]["semantic_ms"],
        "prompt_ms": data["timings"]["prompt_ms"],
        "model_ms": data["timings"]["model_ms"],
        "summary_update_ms": data["timings"]["summary_update_ms"],
        "write_ms": data["timings"]["write_ms"],
        "total_ms": data["timings"]["total_ms"],
        "answer_preview": data["answer"][:140].replace("\n", " "),
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    with httpx.Client() as client:
        for idx, case in enumerate(CHAT_CASES, start=1):
            print(f"[{idx}/{len(CHAT_CASES)}] {case['label']}")
            row = run_chat_case(client, case)
            rows.append(row)
            print(
                f"  total={row['total_ms']} ms | model={row['model_ms']} ms | summary={row['summary_update_ms']} ms"
            )

        debug_row = run_debug_case(
            client,
            session_id="sess-bench-001",
            semantic_query="What did we decide about durable storage?",
            force_pg_restore=False,
        )
        rows.append(debug_row)
        print(
            f"debug | recent={debug_row['recent_count']} | semantic_matches={debug_row['semantic_match_count']}"
        )

    fieldnames = sorted({k for row in rows for k in row.keys()})
    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()