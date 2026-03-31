from __future__ import annotations

import time
from dataclasses import dataclass

from cache_policy import CacheTTLPolicy
from cache_store import CacheStats, RedisExactCache
from cache_wrappers import (
    CacheContext,
    get_or_embed,
    get_or_retrieve,
    get_or_rerank,
    get_or_compress,
    get_or_answer,
)
from normalize import normalize_query


def estimate_tokens(
    query: str, recent_context: str, semantic_context: str, compressed: list[dict]
) -> int:
    text = (
        query
        + "\n"
        + recent_context
        + "\n"
        + semantic_context
        + "\n"
        + "\n".join(x.get("text", "") for x in compressed)
    )
    return max(1, len(text) // 4)


def build_recent_context(messages: list[dict], limit: int = 6) -> str:
    selected = messages[-limit:]
    return "\n".join(
        f'{m.get("role","unknown")}: {m.get("content","")}' for m in selected
    )


def build_semantic_context(messages: list[dict], limit: int = 4) -> str:
    selected = messages[:limit]
    return "\n".join(
        f'{m.get("role","unknown")}: {m.get("content","")}' for m in selected
    )


@dataclass
class PipelineResult:
    query: str
    answer: str
    retrieved_ids: list[str]
    reranked_ids: list[str]
    final_context_ids: list[str]
    prompt_tokens: int
    ttft_ms: float
    total_latency_ms: float
    compression_ratio: float
    cache_stats: dict
    reranked_count: int
    deduped_count: int
    duplicate_reduction_rate: float
    cluster_coverage: int

class RetrievalPipeline:
    def __init__(
        self,
        session_memory,
        embedder,
        doc_store,
        reranker,
        compressor,
        generator,
        retrieve_top_k: int = 20,
        rerank_top_k: int = 5,
        compress_top_k: int = 3,
        final_context_dedupe=None,
    ):
        self.session_memory = session_memory
        self.embedder = embedder
        self.doc_store = doc_store
        self.reranker = reranker
        self.compressor = compressor
        self.generator = generator
        self.retrieve_top_k = retrieve_top_k
        self.rerank_top_k = rerank_top_k
        self.compress_top_k = compress_top_k
        self.final_context_dedupe = final_context_dedupe

    def total_text_chars(self, items: list[dict]) -> int:
        return sum(len(x.get("text", "")) for x in items)

    async def run_baseline(self, query: str) -> PipelineResult:
        start = time.perf_counter()
        normalized_query = normalize_query(query)

        recent_context = build_recent_context(self.session_memory.recent_messages())
        semantic_context = build_semantic_context(
            self.session_memory.semantic_messages()
        )

        _ = await self.embedder.embed_query(normalized_query)
        retrieved = await self.doc_store.retrieve(
            normalized_query,
            top_k=self.retrieve_top_k,
        )
        reranked = await self.reranker.rerank(
            normalized_query,
            retrieved,
            top_k=self.rerank_top_k,
        )

        if self.final_context_dedupe is not None:
            reranked_for_compression = self.final_context_dedupe.dedupe(
                reranked,
                max_items=self.compress_top_k,
            )
        else:
            reranked_for_compression = reranked[: self.compress_top_k]

        compressed = await self.compressor.compress(
            normalized_query,
            reranked_for_compression,
            top_k=self.compress_top_k,
        )
        answer_start = time.perf_counter()
        answer = await self.generator.answer(
            normalized_query,
            recent_context,
            semantic_context,
            compressed,
        )
        ttft_ms = (time.perf_counter() - answer_start) * 1000.0
        total_latency_ms = (time.perf_counter() - start) * 1000.0

        self.session_memory.add_exchange(query, answer)
        retrieved_text_chars = self.total_text_chars(reranked)
        compressed_text_chars = self.total_text_chars(compressed)
        compression_ratio = (
            compressed_text_chars / retrieved_text_chars
            if retrieved_text_chars > 0
            else 0.0
        )
        reranked_count = len(reranked)
        deduped_count = len(reranked_for_compression)
        duplicate_reduction_rate = (
            1.0 - (deduped_count / reranked_count)
            if reranked_count > 0
            else 0.0
        )

        cluster_coverage = len(
            {
                x.get("metadata", {}).get("cluster_id")
                for x in reranked_for_compression
                if x.get("metadata", {}).get("cluster_id") is not None
            }
        )
        return PipelineResult(
            query=query,
            answer=answer,
            retrieved_ids=[x["id"] for x in retrieved],
            reranked_ids=[x["id"] for x in reranked],
            final_context_ids=[x["id"] for x in compressed],
            prompt_tokens=estimate_tokens(
                query, recent_context, semantic_context, compressed
            ),
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            compression_ratio=compression_ratio,
            cache_stats={},
            reranked_count=reranked_count,
            deduped_count=deduped_count,
            duplicate_reduction_rate=duplicate_reduction_rate,
            cluster_coverage=cluster_coverage,
        )

    async def run_cached(
        self,
        query: str,
        redis_client,
        corpus_version: str,
        embedding_model: str,
        reranker_model: str,
        compressor_version: str,
        generator_version: str,
        source_class: str = "stable",
        strict_freshness: bool = True,
    ) -> PipelineResult:
        start = time.perf_counter()
        normalized_query = normalize_query(query)

        recent_context = build_recent_context(self.session_memory.recent_messages())
        semantic_context = build_semantic_context(
            self.session_memory.semantic_messages()
        )

        stats = CacheStats()
        cache = RedisExactCache(redis_client=redis_client, prefix="lab9")
        ttl_policy = CacheTTLPolicy()

        ctx = CacheContext(
            cache=cache,
            stats=stats,
            ttl_policy=ttl_policy,
            embedding_model=embedding_model,
            reranker_model=reranker_model,
            compressor_version=compressor_version,
            generator_version=generator_version,
            corpus_version=corpus_version,
            source_class=source_class,
            strict_freshness=strict_freshness,
        )

        query_vector= await get_or_embed(
            ctx,
            normalized_query,
            self.embedder.embed_query,
        )

        retrieved = await get_or_retrieve(
            ctx,
            normalized_query,
            self.retrieve_top_k,
            lambda q, top_k: self.doc_store.retrieve(q, top_k),
        )

        reranked = await get_or_rerank(
            ctx,
            normalized_query,
            retrieved,
            self.rerank_top_k,
            self.reranker.rerank,
        )

        if self.final_context_dedupe is not None:
            reranked_for_compression = self.final_context_dedupe.dedupe(
                reranked,
                max_items=self.compress_top_k,
            )
        else:
            reranked_for_compression = reranked[: self.compress_top_k]

        compressed = await get_or_compress(
            ctx,
            normalized_query,
            reranked_for_compression,
            self.compress_top_k,
            self.compressor.compress,
        )
        answer_start = time.perf_counter()
        answer = await get_or_answer(
            ctx,
            normalized_query,
            recent_context,
            semantic_context,
            compressed,
            self.generator.answer,
        )
        ttft_ms = (time.perf_counter() - answer_start) * 1000.0
        total_latency_ms = (time.perf_counter() - start) * 1000.0

        self.session_memory.add_exchange(query, answer)
        retrieved_text_chars = self.total_text_chars(reranked)
        compressed_text_chars = self.total_text_chars(compressed)
        compression_ratio = (
            compressed_text_chars / retrieved_text_chars
            if retrieved_text_chars > 0
            else 0.0
        )
        reranked_count = len(reranked)
        deduped_count = len(reranked_for_compression)
        duplicate_reduction_rate = (
            1.0 - (deduped_count / reranked_count)
            if reranked_count > 0
            else 0.0
        )

        cluster_coverage = len(
            {
                x.get("metadata", {}).get("cluster_id")
                for x in reranked_for_compression
                if x.get("metadata", {}).get("cluster_id") is not None
            }
        )
        return PipelineResult(
            query=query,
            answer=answer,
            retrieved_ids=[x["id"] for x in retrieved],
            reranked_ids=[x["id"] for x in reranked],
            final_context_ids=[x["id"] for x in compressed],
            prompt_tokens=estimate_tokens(
                query, recent_context, semantic_context, compressed
            ),
            ttft_ms=ttft_ms,
            total_latency_ms=total_latency_ms,
            compression_ratio=compression_ratio,
            cache_stats=stats.as_dict(),
            reranked_count=reranked_count,
            deduped_count=deduped_count,
            duplicate_reduction_rate=duplicate_reduction_rate,
            cluster_coverage=cluster_coverage,
        )
