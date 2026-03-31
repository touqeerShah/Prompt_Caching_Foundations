from __future__ import annotations

import asyncio
from typing import Any, List

from sentence_transformers import CrossEncoder


class CrossEncoderRerankerAdapter:
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-base",
        max_length: int = 512,
        batch_size: int = 16,
    ):
        self.model_name = model_name
        self.max_length = max_length
        self.batch_size = batch_size
        self.model = CrossEncoder(
            model_name,
            max_length=max_length,
        )

    async def rerank(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        if not candidates:
            return []

        return await asyncio.to_thread(
            self._rerank_sync,
            query,
            candidates,
            top_k,
        )

    def _rerank_sync(
        self,
        query: str,
        candidates: list[dict[str, Any]],
        top_k: int,
    ) -> list[dict[str, Any]]:
        pairs = []
        filtered_candidates: list[dict[str, Any]] = []

        for item in candidates:
            text = item.get("text", "")
            if not text:
                continue
            pairs.append((query, text))
            filtered_candidates.append(item)

        if not filtered_candidates:
            return []

        scores = self.model.predict(
            pairs,
            batch_size=self.batch_size,
            show_progress_bar=False,
        )

        rescored: list[dict[str, Any]] = []
        for item, score in zip(filtered_candidates, scores):
            out = dict(item)
            out["rerank_score"] = float(score)
            rescored.append(out)

        rescored.sort(key=lambda x: x["rerank_score"], reverse=True)
        return rescored[:top_k]
