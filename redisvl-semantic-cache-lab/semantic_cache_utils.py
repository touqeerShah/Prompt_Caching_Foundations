from __future__ import annotations

from typing import Dict, Any

from redisvl.extensions.llmcache import SemanticCache
from redisvl.utils.vectorize import HFTextVectorizer

SYSTEM_PROMPT = """You are a helpful support assistant.
Answer clearly and briefly.
Use stable support guidance.
If the answer depends on account-specific or real-time information, say that fresh lookup is required.
"""

ORG_POLICY = {
    "tone": "professional",
    "risk_policy": "do not guess account-specific or real-time facts",
}

EMBED_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def normalize_text(text: str) -> str:
    lines = [line.rstrip() for line in text.strip().splitlines()]
    return "\n".join(lines)


def build_semantic_prompt(user_message: str, category: str = "faq") -> str:
    return (
        "[SYSTEM]\n"
        f"{normalize_text(SYSTEM_PROMPT)}\n\n"
        "[ORG_POLICY]\n"
        f"{ORG_POLICY}\n\n"
        "[CATEGORY]\n"
        f"{category}\n\n"
        "[USER]\n"
        f"{normalize_text(user_message)}"
    )


def make_cache() -> SemanticCache:
    vectorizer = HFTextVectorizer(model=EMBED_MODEL)

    cache = SemanticCache(
        name="faq-semantic-cache",
        vectorizer=vectorizer,
        distance_threshold=0.2,
        ttl=3600,
        filterable_fields=[
            {"name": "tenant_id", "type": "tag"},
            {"name": "language", "type": "tag"},
            {"name": "version", "type": "tag"},
            {"name": "category", "type": "tag"},
        ],
        redis_url="redis://localhost:6379",
        overwrite=False,
    )
    return cache


def cache_metadata(
    tenant_id: str,
    language: str = "en",
    version: str = "v1",
    category: str = "faq",
) -> Dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "language": language,
        "version": version,
        "category": category,
    }