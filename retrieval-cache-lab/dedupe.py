from __future__ import annotations

from typing import Any
from redisvl.utils.vectorize import HFTextVectorizer


def cosine_similarity(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


class FinalContextDedupe:
    def __init__(self, embedding_model: str, threshold: float = 0.94):
        self.vectorizer = HFTextVectorizer(model=embedding_model)
        self.threshold = threshold

    def dedupe(self, items: list[dict[str, Any]], max_items: int | None = None) -> list[dict[str, Any]]:
        if not items:
            return []

        texts = [x.get("text", "") for x in items]
        vectors = self.vectorizer.embed_many(texts)

        kept_items = []
        kept_vectors = []

        for item, vec in zip(items, vectors):
            duplicate = False
            for kept_vec in kept_vectors:
                if cosine_similarity(vec, kept_vec) >= self.threshold:
                    duplicate = True
                    break
            if not duplicate:
                kept_items.append(item)
                kept_vectors.append(vec)
            if max_items is not None and len(kept_items) >= max_items:
                break

        return kept_items