from __future__ import annotations

import asyncio
import re
from typing import Any, List

from redisvl.utils.vectorize import HFTextVectorizer


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0

    dot = 0.0
    norm_a = 0.0
    norm_b = 0.0
    for x, y in zip(a, b):
        dot += x * y
        norm_a += x * x
        norm_b += y * y

    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0

    return dot / ((norm_a ** 0.5) * (norm_b ** 0.5))


def split_sentences(text: str) -> list[str]:
    text = " ".join(text.split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p.strip()]


class ExtractiveCompressorAdapter:
    def __init__(
        self,
        embedding_model: str,
        sentences_per_chunk: int = 2,
        min_sentence_chars: int = 25,
    ):
        self.embedding_model = embedding_model
        self.sentences_per_chunk = sentences_per_chunk
        self.min_sentence_chars = min_sentence_chars
        self.vectorizer = HFTextVectorizer(model=embedding_model)

    async def compress(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        return await asyncio.to_thread(
            self._compress_sync,
            query,
            candidates,
            top_k,
        )

    def _compress_sync(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        query_vec = self.vectorizer.embed(query)
        compressed_rows: list[dict[str, Any]] = []

        for item in candidates[:top_k]:
            text = item.get("text", "")
            if not text:
                continue

            sentences = [
                s for s in split_sentences(text)
                if len(s) >= self.min_sentence_chars
            ]

            if not sentences:
                compressed_text = text[:300].strip()
                compressed_rows.append(
                    {
                        "id": item["id"],
                        "text": compressed_text,
                        "score": float(item.get("rerank_score", item.get("score", 0.0))),
                        "metadata": {
                            **item.get("metadata", {}),
                            "compression_method": "fallback_truncate",
                            "source_id": item["id"],
                        },
                    }
                )
                continue

            sentence_vectors = self.vectorizer.embed_many(sentences)

            scored_sentences = []
            for sent, sent_vec in zip(sentences, sentence_vectors):
                sent_score = cosine_similarity(query_vec, sent_vec)
                scored_sentences.append((sent, float(sent_score)))

            scored_sentences.sort(key=lambda x: x[1], reverse=True)
            selected = scored_sentences[: self.sentences_per_chunk]

            # restore original order among selected sentences
            selected_texts = [s for s, _ in selected]
            ordered_selected = [s for s in sentences if s in selected_texts]

            compressed_text = " ".join(ordered_selected).strip()

            compressed_rows.append(
                {
                    "id": item["id"],
                    "text": compressed_text,
                    "score": float(item.get("rerank_score", item.get("score", 0.0))),
                    "metadata": {
                        **item.get("metadata", {}),
                        "compression_method": "extractive_similarity",
                        "source_id": item["id"],
                        "selected_sentence_count": len(ordered_selected),
                        "original_sentence_count": len(sentences),
                    },
                }
            )

        return compressed_rows[:top_k]