from __future__ import annotations

import json
from typing import Any, Dict, List


SYSTEM_PROMPT = """You are a helpful assistant.
Answer clearly and briefly.
Use the provided context when relevant.
If context is insufficient, say what is missing.
"""

TOOLS = [
    {
        "name": "search_docs",
        "description": "Search internal documents",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "top_k": {"type": "integer"},
            },
            "required": ["query"],
        },
    }
]

ORG_POLICY = {
    "tone": "professional",
    "citation_policy": "cite supplied context when possible",
    "privacy_policy": "do not reveal secrets",
}

REFERENCE_DOC = """
Prompt caching works best when the repeated prefix remains identical across calls.
Stable instructions, stable tool schemas, and stable reference text should appear before the user question.
Dynamic user-specific data should be placed later in the prompt when possible.
""".strip()


def stable_json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_prompt(user_question: str) -> str:
    return (
        "[SYSTEM]\n"
        f"{SYSTEM_PROMPT.strip()}\n\n"
        "[ORG_POLICY]\n"
        f"{stable_json(ORG_POLICY)}\n\n"
        "[TOOLS]\n"
        f"{stable_json(TOOLS)}\n\n"
        "[REFERENCE]\n"
        f"{REFERENCE_DOC}\n\n"
        "[USER]\n"
        f"{user_question.strip()}\n\n"
        "[ASSISTANT]\n"
    )


def unstable_prompt(user_question: str) -> str:
    # intentionally less cache-friendly
    return (
        "[USER]\n"
        f"   {user_question}   \n\n"
        "[REFERENCE]\n"
        f"{REFERENCE_DOC}\n\n\n"
        "[TOOLS]\n"
        f"{json.dumps(TOOLS, ensure_ascii=False, indent=2)}\n\n"
        "[ORG_POLICY]\n"
        f"{json.dumps(ORG_POLICY, ensure_ascii=False, indent=2)}\n\n"
        "[SYSTEM]\n"
        f"{SYSTEM_PROMPT}\n\n"
        "[ASSISTANT]\n"
    )