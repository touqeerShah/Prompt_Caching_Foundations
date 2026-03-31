from __future__ import annotations

import asyncio
from typing import Any

import httpx


def build_context_block(compressed: list[dict[str, Any]]) -> str:
    lines: list[str] = []
    for idx, item in enumerate(compressed, start=1):
        chunk_id = item.get("id", f"chunk-{idx}")
        text = item.get("text", "").strip()
        lines.append(f"[{idx}] {chunk_id}\n{text}")
    return "\n\n".join(lines)


def build_prompt(
    query: str,
    recent_context: str,
    semantic_context: str,
    compressed: list[dict[str, Any]],
) -> str:
    evidence_block = build_context_block(compressed)

    return f"""You are a retrieval-grounded assistant.
Answer the user using only the provided evidence and relevant session context.
If the evidence is insufficient, say that clearly.
Do not invent facts.
Prefer concise, direct answers.

Recent conversation context:
{recent_context or "(none)"}

Semantically relevant prior context:
{semantic_context or "(none)"}

Retrieved evidence:
{evidence_block or "(none)"}

User question:
{query}

Instructions:
- Use the evidence first.
- If the answer is partially supported, say what is supported and what is unclear.
- Do not mention internal implementation details.
- When useful, cite chunk ids like [1], [2].

Answer:
""".strip()


class OllamaGeneratorAdapter:
    def __init__(
        self,
        model_name: str = "llama3.1:8b",
        base_url: str = "http://localhost:11434",
        temperature: float = 0.1,
        timeout_seconds: float = 120.0,
    ):
        self.model_name = model_name
        self.base_url = base_url.rstrip("/")
        self.temperature = temperature
        self.timeout_seconds = timeout_seconds

    async def answer(
        self,
        query: str,
        recent_context: str,
        semantic_context: str,
        compressed: list[dict[str, Any]],
    ) -> str:
        prompt = build_prompt(
            query=query,
            recent_context=recent_context,
            semantic_context=semantic_context,
            compressed=compressed,
        )

        payload = {
            "model": self.model_name,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
            },
        }

        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(
                f"{self.base_url}/api/generate",
                json=payload,
            )
            response.raise_for_status()
            data = response.json()

        text = (data.get("response") or "").strip()
        if not text:
            return "I could not generate an answer from the provided evidence."
        return text