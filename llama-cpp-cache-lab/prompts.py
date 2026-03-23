from __future__ import annotations

import json

SYSTEM_PROMPT = """You are a helpful assistant.
Answer clearly and briefly.
Use the provided context when relevant.
If context is insufficient, say what is missing.
"""

ORG_POLICY = {
    "tone": "professional",
    "citation_policy": "cite supplied context when possible",
    "privacy_policy": "do not reveal secrets",
}

REFERENCE_DOC = """
Prompt/session reuse works best when a long prefix remains stable.
If the system instructions and reference text stay identical, later requests can reuse prior work more effectively.
If you change early tokens in the prefix, reuse usually drops.
""".strip()


def stable_json(data) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def canonical_prompt(user_question: str) -> str:
    return (
        "[SYSTEM]\n"
        f"{SYSTEM_PROMPT.strip()}\n\n"
        "[ORG_POLICY]\n"
        f"{stable_json(ORG_POLICY)}\n\n"
        "[REFERENCE]\n"
        f"{REFERENCE_DOC}\n\n"
        "[USER]\n"
        f"{user_question.strip()}\n\n"
        "[ASSISTANT]\n"
    )


def changed_early_prefix_prompt(user_question: str) -> str:
    # Deliberately modifies the early prefix to show invalidation behavior
    modified_system = SYSTEM_PROMPT.replace("briefly", "concisely")
    return (
        "[SYSTEM]\n"
        f"{modified_system.strip()}\n\n"
        "[ORG_POLICY]\n"
        f"{stable_json(ORG_POLICY)}\n\n"
        "[REFERENCE]\n"
        f"{REFERENCE_DOC}\n\n"
        "[USER]\n"
        f"{user_question.strip()}\n\n"
        "[ASSISTANT]\n"
    )