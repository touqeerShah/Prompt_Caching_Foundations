from __future__ import annotations

import hashlib
import json
import random
from typing import Any, Dict, List, Optional


SYSTEM_INSTRUCTIONS = """You are a helpful assistant.
Answer clearly and briefly.
Use provided context when relevant.
If context is insufficient, say what is missing.
"""

ORG_POLICY = {
    "tone": "professional",
    "citation_policy": "cite context when available",
    "privacy_policy": "do not reveal secrets",
}

TOOL_SCHEMAS = [
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
    },
    {
        "name": "lookup_user_profile",
        "description": "Look up the user's profile configuration",
        "parameters": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
            },
            "required": ["user_id"],
        },
    },
]


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def normalize_whitespace(text: str) -> str:
    # this function collapses multiple blank lines and trims leading/trailing whitespace
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


def stable_json(data: Any) -> str:
    # this function produces deterministic JSON with sorted keys and no extra whitespace
    return json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def unstable_json(data: Any) -> str:
    # this function produces non-deterministic JSON with default settings (for testing purposes)
    return json.dumps(data, ensure_ascii=False, sort_keys=False, indent=2)


def sort_docs_deterministically(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return sorted(docs, key=lambda d: (d.get("id", ""), d.get("text", "")))


def build_prompt_version_a(
    user_message: str,
    retrieved_docs: List[Dict[str, Any]],
    tenant_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    BAD:
    - random ordering
    - extra whitespace
    - dynamic/user data near the top
    - non-canonical JSON
    """
    sections = [
        ("user_message", f"[USER_MESSAGE]\n\n{user_message}\n"),
        ("tenant_config", f"[TENANT]\n{unstable_json(tenant_config)}\n"),
        ("system", f"[SYSTEM]\n\n{SYSTEM_INSTRUCTIONS}\n"),
        ("org_policy", f"[ORG_POLICY]\n{unstable_json(ORG_POLICY)}\n"),
        ("tools", f"[TOOLS]\n{unstable_json(TOOL_SCHEMAS)}\n"),
        (
            "context",
            "[CONTEXT]\n"
            + "\n".join(f"- {doc['id']}: {doc['text']}" for doc in retrieved_docs)
            + "\n",
        ),
    ]

    random.shuffle(sections)

    prompt = (
        "\n\n\n".join(section_text for _, section_text in sections)
        + "\n\n[ASSISTANT]\n"
    )
    return {
        "full_prompt": prompt,
        "static_prefix": "",  # intentionally bad / not isolated
    }


def build_prompt_version_b(
    user_message: str,
    retrieved_docs: List[Dict[str, Any]],
    tenant_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    BETTER:
    - stable instructions first
    - context after instructions
    - user question last
    - still not fully canonical
    """
    tools_json = unstable_json(TOOL_SCHEMAS)
    org_policy_json = unstable_json(ORG_POLICY)
    tenant_json = unstable_json(tenant_config)

    static_prefix = (
        "[SYSTEM]\n"
        f"{normalize_whitespace(SYSTEM_INSTRUCTIONS)}\n\n"
        "[ORG_POLICY]\n"
        f"{org_policy_json}\n\n"
        "[TOOLS]\n"
        f"{tools_json}\n\n"
        "[TENANT]\n"
        f"{tenant_json}\n"
    )

    context_block = (
        "[CONTEXT]\n"
        + "\n".join(f"- {doc['id']}: {doc['text']}" for doc in retrieved_docs)
        + "\n"
    )

    dynamic_suffix = f"{context_block}\n[USER]\n{user_message}\n\n[ASSISTANT]\n"

    return {
        "full_prompt": static_prefix + "\n" + dynamic_suffix,
        "static_prefix": static_prefix,
    }


def build_prompt_version_c(
    user_message: str,
    retrieved_docs: List[Dict[str, Any]],
    tenant_config: Dict[str, Any],
) -> Dict[str, str]:
    """
    BEST:
    - static prefix isolated
    - canonical whitespace
    - stable JSON serialization
    - deterministic ordering
    - dynamic suffix only changes where needed
    """
    canonical_system = normalize_whitespace(SYSTEM_INSTRUCTIONS)
    canonical_org_policy = stable_json(ORG_POLICY)
    canonical_tools = stable_json(sorted(TOOL_SCHEMAS, key=lambda t: t["name"]))
    canonical_tenant = stable_json(tenant_config)

    sorted_docs = sort_docs_deterministically(retrieved_docs)
    canonical_context = "\n".join(
        f"- ({doc['id']}) {normalize_whitespace(doc['text'])}" for doc in sorted_docs
    )

    static_prefix = (
        "[SYSTEM]\n"
        f"{canonical_system}\n\n"
        "[ORG_POLICY]\n"
        f"{canonical_org_policy}\n\n"
        "[TOOLS]\n"
        f"{canonical_tools}\n\n"
        "[TENANT]\n"
        f"{canonical_tenant}\n"
    )

    dynamic_suffix = (
        "[CONTEXT]\n"
        f"{canonical_context}\n\n"
        "[USER]\n"
        f"{normalize_whitespace(user_message)}\n\n"
        "[ASSISTANT]\n"
    )

    return {
        "full_prompt": static_prefix + "\n" + dynamic_suffix,
        "static_prefix": static_prefix,
    }


def prompt_metrics(full_prompt: str, static_prefix: str) -> Dict[str, Any]:
    return {
        "full_prompt_sha256": sha256_text(full_prompt),
        "static_prefix_sha256": sha256_text(static_prefix) if static_prefix else None,
        "full_prompt_chars": len(full_prompt),
        "static_prefix_chars": len(static_prefix),
    }


def common_prefix_chars(a: str, b: str) -> int:
    n = min(len(a), len(b))
    i = 0
    while i < n and a[i] == b[i]:
        i += 1
    return i


def prefix_similarity_ratio(a: str, b: str) -> float:
    if not a and not b:
        return 1.0
    denom = max(len(a), len(b), 1)
    return round(common_prefix_chars(a, b) / denom, 4)
