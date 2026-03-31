from __future__ import annotations

import asyncio
from pathlib import Path

from config import Settings
from redis_client import build_redis_client
from chunking import chunk_text
from doc_store import RedisDocumentStoreAdapter


async def ingest_text_file(
    file_path: str,
    document_id: str | None = None,
) -> None:
    settings = Settings()
    redis_client = build_redis_client(settings)

    store = RedisDocumentStoreAdapter(
        redis_client=redis_client,
        index_name=settings.doc_index_name,
        embedding_model=settings.embedding_model,
    )

    path = Path(file_path)
    text = path.read_text(encoding="utf-8")
    document_id = document_id or path.stem

    chunks = chunk_text(
        document_id=document_id,
        text=text,
        chunk_size=800,
        chunk_overlap=120,
        metadata={"source_path": str(path)},
    )

    inserted = await store.add_chunks(chunks)
    print(f"Inserted {inserted} chunks for document_id={document_id}")


if __name__ == "__main__":
    asyncio.run(ingest_text_file("sample_doc.txt"))