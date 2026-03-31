from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, List

from redisvl.utils.vectorize import HFTextVectorizer

from chunking import TextChunk


class RedisDocumentStoreAdapter:
    def __init__(
        self,
        redis_client,
        index_name: str,
        embedding_model: str,
    ):
        self.redis = redis_client
        self.index_name = index_name
        self.vectorizer = HFTextVectorizer(model=embedding_model)

    def _doc_key(self, chunk_id: str) -> str:
        return f"{self.index_name}:chunk:{chunk_id}"

    def _doc_set_key(self) -> str:
        return f"{self.index_name}:chunks"

    async def add_chunks(self, chunks: List[TextChunk]) -> int:
        if not chunks:
            return 0

        texts = [c.text for c in chunks]
        vectors = self.vectorizer.embed_many(texts)

        pipe = self.redis.pipeline()
        count = 0

        for chunk, vector in zip(chunks, vectors):
            payload = {
                "id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "metadata": chunk.metadata,
                "embedding": vector,
            }
            pipe.set(self._doc_key(chunk.chunk_id), json.dumps(payload, ensure_ascii=False))
            pipe.sadd(self._doc_set_key(), chunk.chunk_id)
            count += 1

        pipe.execute()
        return count

    async def retrieve(self, query: str, top_k: int) -> List[dict[str, Any]]:
        query_vector = self.vectorizer.embed(query)

        chunk_ids = self.redis.smembers(self._doc_set_key())
        if not chunk_ids:
            return []

        rows: List[dict[str, Any]] = []
        for raw_chunk_id in chunk_ids:
            chunk_id = raw_chunk_id.decode("utf-8") if isinstance(raw_chunk_id, bytes) else raw_chunk_id
            raw = self.redis.get(self._doc_key(chunk_id))
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            payload = json.loads(raw)
            score = cosine_similarity(query_vector, payload["embedding"])
            rows.append(
                {
                    "id": payload["id"],
                    "text": payload["text"],
                    "score": float(score),
                    "metadata": {
                        "document_id": payload.get("document_id"),
                        "chunk_index": payload.get("chunk_index"),
                        **(payload.get("metadata") or {}),
                    },
                }
            )

        rows.sort(key=lambda x: x["score"], reverse=True)
        return rows[:top_k]
    async def add_chunks_deduped(
        self,
        chunks: list[TextChunk],
        similarity_threshold: float = 0.97,
    ) -> int:
        if not chunks:
            return 0

        existing_chunk_ids = self.redis.smembers(self._doc_set_key())
        existing_rows = []
        for raw_id in existing_chunk_ids:
            cid = raw_id.decode("utf-8") if isinstance(raw_id, bytes) else raw_id
            raw = self.redis.get(self._doc_key(cid))
            if not raw:
                continue
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8")
            existing_rows.append(json.loads(raw))

        inserted = 0
        new_vectors = self.vectorizer.embed_many([c.text for c in chunks])

        pipe = self.redis.pipeline()
        for chunk, vector in zip(chunks, new_vectors):
            duplicate_found = False

            for row in existing_rows:
                if row.get("document_id") != chunk.document_id:
                    continue
                sim = cosine_similarity(vector, row.get("embedding", []))
                if sim >= similarity_threshold:
                    duplicate_found = True
                    break

            if duplicate_found:
                continue

            payload = {
                "id": chunk.chunk_id,
                "document_id": chunk.document_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "metadata": chunk.metadata,
                "embedding": vector,
            }
            pipe.set(self._doc_key(chunk.chunk_id), json.dumps(payload, ensure_ascii=False))
            pipe.sadd(self._doc_set_key(), chunk.chunk_id)
            existing_rows.append(payload)
            inserted += 1

        pipe.execute()
        return inserted

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