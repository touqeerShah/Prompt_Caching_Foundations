from __future__ import annotations

import hashlib
import json


SYSTEM_PROMPT = """You are a helpful assistant.
Answer clearly and briefly.
Use provided context when relevant.
If context is insufficient, say what is missing.
"""

ORG_POLICY = {
    "tone": "professional",
    "citation_policy": "cite supplied context when possible",
    "privacy_policy": "do not reveal secrets",
}


def stable_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


def build_canonical_prompt(user_message: str, context: str = "") -> str:
    parts = [
        "[SYSTEM]\n" + normalize_text(SYSTEM_PROMPT),
        "[ORG_POLICY]\n" + stable_json(ORG_POLICY),
    ]

    if context.strip():
        parts.append("[CONTEXT]\n" + normalize_text(context))

    parts.append("[USER]\n" + normalize_text(user_message))
    parts.append("[ASSISTANT]\n")

    return "\n\n".join(parts)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode("utf-8")).hexdigest()