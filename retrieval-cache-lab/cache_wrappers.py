from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Awaitable

from cache_keys import (
    embedding_cache_key,
    retrieval_cache_key,
    rerank_cache_key,
    compression_cache_key,
    answer_cache_key,
)
from cache_store import CacheStats, RedisExactCache, stable_hash
from cache_policy import choose_layer_ttl, CacheTTLPolicy


@dataclass
class CacheContext:
    cache: RedisExactCache
    stats: CacheStats
    ttl_policy: Any
    embedding_model: str
    reranker_model: str
    compressor_version: str
    generator_version: str
    corpus_version: str
    source_class: str = "stable"
    strict_freshness: bool = True


async def get_or_embed(
    ctx: CacheContext,
    normalized_query: str,
    embed_fn: Callable[[str], Awaitable[list[float]]],
) -> list[float]:
    key = embedding_cache_key(normalized_query, ctx.embedding_model)
    cached = ctx.cache.get_json("embedding", key)
    if cached is not None:
        ctx.stats.embedding_hits += 1
        return cached["data"]

    ctx.stats.embedding_misses += 1
    value = await embed_fn(normalized_query)
    ctx.cache.set_json(
        "embedding",
        key,
        value,
        ttl_seconds=ctx.ttl_policy.embedding_ttl_seconds,
        meta={
            "layer": "embedding",
            "embedding_model": ctx.embedding_model,
        },
    )
    return value


async def get_or_retrieve(
    ctx: CacheContext,
    normalized_query: str,
    top_k: int,
    retrieve_fn,
) -> list[dict[str, Any]]:
    if ctx.strict_freshness:
        key = retrieval_cache_key(
            normalized_query=normalized_query,
            corpus_version=ctx.corpus_version,
            top_k=top_k,
            embedding_model=ctx.embedding_model,
        )
    else:
        key = stable_hash(
            {
                "type": "retrieval",
                "query": normalized_query,
                "top_k": top_k,
                "embedding_model": ctx.embedding_model,
            }
        )

    cached = ctx.cache.get_json("retrieval", key)
    if cached is not None:
        cached_version = (cached.get("meta") or {}).get("corpus_version")
        if cached_version != ctx.corpus_version:
            ctx.stats.stale_evidence_reuse_count += 1
        ctx.stats.retrieval_hits += 1
        return cached["data"]

    ctx.stats.retrieval_misses += 1
    value = await retrieve_fn(normalized_query, top_k)

    ctx.cache.set_json(
        "retrieval",
        key,
        value,
        ttl_seconds=choose_layer_ttl(ctx.ttl_policy, "retrieval", ctx.source_class),
        meta={
            "corpus_version": ctx.corpus_version,
            "source_class": ctx.source_class,
            "layer": "retrieval",
        },
    )
    return value


async def get_or_rerank(
    ctx: CacheContext,
    normalized_query: str,
    candidates: list[dict[str, Any]],
    top_k: int,
    rerank_fn: Callable[
        [str, list[dict[str, Any]], int], Awaitable[list[dict[str, Any]]]
    ],
) -> list[dict[str, Any]]:
    candidate_ids = [x["id"] for x in candidates]
    if ctx.strict_freshness:
        key = rerank_cache_key(
            normalized_query=normalized_query,
            candidate_ids=candidate_ids,
            reranker_model=ctx.reranker_model,
            top_k=top_k,
            corpus_version=ctx.corpus_version,
        )
    else:
        key = stable_hash(
            {
                "type": "rerank",
                "query": normalized_query,
                "candidate_ids": candidate_ids,
                "top_k": top_k,
                "embedding_model": ctx.embedding_model,
            }
        )
    cached = ctx.cache.get_json("rerank", key)

    if cached is not None:
        cached_version = (cached.get("meta") or {}).get("corpus_version")
        if cached_version != ctx.corpus_version:
            ctx.stats.stale_evidence_reuse_count += 1
        ctx.stats.rerank_hits += 1
        return cached["data"]
    ctx.stats.rerank_misses += 1
    value = await rerank_fn(normalized_query, candidates, top_k)
    ctx.cache.set_json(
        "rerank",
        key,
        value,
        ttl_seconds=choose_layer_ttl(ctx.ttl_policy, "rerank", ctx.source_class),
        meta={
            "corpus_version": ctx.corpus_version,
            "source_class": ctx.source_class,
            "layer": "rerank",
        },
    )
    return value


async def get_or_compress(
    ctx: CacheContext,
    normalized_query: str,
    reranked: list[dict[str, Any]],
    top_k: int,
    compress_fn: Callable[
        [str, list[dict[str, Any]], int], Awaitable[list[dict[str, Any]]]
    ],
) -> list[dict[str, Any]]:
    reranked_ids = [x["id"] for x in reranked]
    if ctx.strict_freshness:
        key = compression_cache_key(
            normalized_query=normalized_query,
            reranked_ids=reranked_ids,
            compressor_version=ctx.compressor_version,
            top_k=top_k,
            corpus_version=ctx.corpus_version,
        )
    else:
        key = stable_hash(
            {
                "type": "compression",
                "query": normalized_query,
                "reranked_ids": reranked_ids,
                "compressor_version": ctx.compressor_version,
                "top_k": top_k,
            }
        )
    cached = ctx.cache.get_json("compression", key)

    if cached is not None:
        cached_version = (cached.get("meta") or {}).get("corpus_version")
        if cached_version != ctx.corpus_version:
            ctx.stats.stale_evidence_reuse_count += 1
        ctx.stats.compression_hits += 1
        return cached["data"]
    ctx.stats.compression_misses += 1
    value = await compress_fn(normalized_query, reranked, top_k)
    ctx.cache.set_json(
        "compression",
        key,
        value,
        ttl_seconds=choose_layer_ttl(ctx.ttl_policy, "compression", ctx.source_class),
        meta={
            "corpus_version": ctx.corpus_version,
            "source_class": ctx.source_class,
            "layer": "compression",
        },
    )
    return value


async def get_or_answer(
    ctx: CacheContext,
    normalized_query: str,
    recent_context: str,
    semantic_context: str,
    compressed: list[dict[str, Any]],
    answer_fn: Callable[[str, str, str, list[dict[str, Any]]], Awaitable[str]],
) -> str:
    context_hash = stable_hash(
        {
            "recent_context": recent_context,
            "semantic_context": semantic_context,
            "compressed_ids": [x["id"] for x in compressed],
            "compressed_texts": [x.get("text", "") for x in compressed],
        }
    )
    if ctx.strict_freshness:
        key = answer_cache_key(
            normalized_query=normalized_query,
            context_hash=context_hash,
            generator_version=ctx.generator_version,
            corpus_version=ctx.corpus_version,
        )
    else:
        key = stable_hash(
            {
                "type": "answer",
                "query": normalized_query,
                "embedding_model": ctx.embedding_model,
            }
        )
    cached = ctx.cache.get_json("answer", key)

    if cached is not None:
        cached_version = (cached.get("meta") or {}).get("corpus_version")
        if cached_version != ctx.corpus_version:
            ctx.stats.stale_answer_reuse_count += 1
        ctx.stats.answer_hits += 1
        return cached["data"]
    ctx.stats.answer_misses += 1
    value = await answer_fn(
        normalized_query,
        recent_context,
        semantic_context,
        compressed,
    )
    ctx.cache.set_json(
        "answer",
        key,
        value,
        ttl_seconds=choose_layer_ttl(ctx.ttl_policy, "answer", ctx.source_class),
        meta={
            "corpus_version": ctx.corpus_version,
            "source_class": ctx.source_class,
            "layer": "answer",
        },
    )
    return value
