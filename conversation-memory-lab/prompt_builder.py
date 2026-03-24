from __future__ import annotations

import json
from typing import Any, Dict, List, Optional


SYSTEM_PROMPT = """You are a helpful assistant.
Use the conversation summary for continuity.
Use recent messages for local coherence.
Use recalled messages only when relevant.
If tool data is stale or missing, say so clearly.
"""


def format_messages(messages: List[Dict[str, Any]]) -> str:
    lines = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        lines.append(f"{role.upper()}: {content}")
    return "\n".join(lines)


def build_prompt(
    user_message: str,
    summary: str,
    recent_messages: List[Dict[str, Any]],
    relevant_messages: List[Dict[str, Any]],
    last_tool_result: Optional[Dict[str, Any]] = None,
) -> str:
    parts = [
        "[SYSTEM]\n" + SYSTEM_PROMPT.strip(),
    ]

    if summary.strip():
        parts.append("[RUNNING_SUMMARY]\n" + summary.strip())

    if recent_messages:
        parts.append("[RECENT_MESSAGES]\n" + format_messages(recent_messages))

    if relevant_messages:
        parts.append("[SEMANTIC_RECALL]\n" + format_messages(relevant_messages))

    if last_tool_result:
        parts.append(
            "[LAST_TOOL_RESULT]\n" + json.dumps(last_tool_result, ensure_ascii=False, indent=2)
        )

    parts.append("[USER]\n" + user_message.strip())
    parts.append("[ASSISTANT]\n")

    return "\n\n".join(parts)