from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class TextChunk:
    chunk_id: str
    document_id: str
    text: str
    chunk_index: int
    metadata: dict


def chunk_text(
    document_id: str,
    text: str,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
    metadata: dict | None = None,
) -> List[TextChunk]:
    if chunk_size <= 0:
        raise ValueError("chunk_size must be > 0")
    if chunk_overlap < 0:
        raise ValueError("chunk_overlap must be >= 0")
    if chunk_overlap >= chunk_size:
        raise ValueError("chunk_overlap must be smaller than chunk_size")

    metadata = metadata or {}
    clean = " ".join(text.split())
    if not clean:
        return []

    chunks: List[TextChunk] = []
    start = 0
    idx = 0

    while start < len(clean):
        end = min(len(clean), start + chunk_size)
        chunk_text_value = clean[start:end].strip()
        if chunk_text_value:
            chunks.append(
                TextChunk(
                    chunk_id=f"{document_id}::chunk::{idx}",
                    document_id=document_id,
                    text=chunk_text_value,
                    chunk_index=idx,
                    metadata=metadata.copy(),
                )
            )
        if end >= len(clean):
            break
        start = end - chunk_overlap
        idx += 1

    return chunks
