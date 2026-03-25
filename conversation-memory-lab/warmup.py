from __future__ import annotations

from typing import Any, Dict

from memory_store import save_summary, save_session_meta, save_last_tool_result

WARM_SESSIONS = [
    {
        "session_id": "warm:tenant-001:default-support",
        "summary": "- Default support memory for tenant-001\n- Use Redis for hot memory\n- Use Postgres for durable fallback",
        "meta": {"tenant_id": "tenant-001", "kind": "warm_default"},
        "last_tool_result": {"tool": "config_loader", "result": {"region": "eu", "language": "en"}},
    }
]


def run_startup_warmup() -> dict[str, Any]:
    warmed = 0

    for item in WARM_SESSIONS:
        save_summary(item["session_id"], item["summary"])
        save_session_meta(item["session_id"], item["meta"])
        save_last_tool_result(item["session_id"], item["last_tool_result"])
        warmed += 1

    return {"warmed_sessions": warmed}