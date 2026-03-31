from __future__ import annotations

import asyncio
from redisvl.utils.vectorize import HFTextVectorizer


class HFEmbedderAdapter:
    def __init__(self, model_name: str):
        self.model_name = model_name
        self.vectorizer = HFTextVectorizer(model=model_name)

    async def embed_query(self, query: str) -> list[float]:
        return await asyncio.to_thread(self.vectorizer.embed, query)