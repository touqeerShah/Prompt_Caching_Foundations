from __future__ import annotations

from cache_store import stable_hash


def embedding_cache_key(normalized_query: str, embedding_model: str) -> str:
    return stable_hash(
        {
            "type": "embedding",
            "query": normalized_query,
            "embedding_model": embedding_model,
        }
    )


def retrieval_cache_key(
    normalized_query: str,
    corpus_version: str,
    top_k: int,
    embedding_model: str,
) -> str:
    return stable_hash(
        {
            "type": "retrieval",
            "query": normalized_query,
            "corpus_version": corpus_version,
            "top_k": top_k,
            "embedding_model": embedding_model,
        }
    )

def rerank_cache_key(
    normalized_query: str,
    candidate_ids: list[str],
    reranker_model: str,
    top_k: int,
    corpus_version: str,
) -> str:
    return stable_hash(
        {
            "type": "rerank",
            "query": normalized_query,
            "candidate_ids": candidate_ids,
            "reranker_model": reranker_model,
            "top_k": top_k,
            "corpus_version": corpus_version,
        }
    )


def compression_cache_key(
    normalized_query: str,
    reranked_ids: list[str],
    compressor_version: str,
    top_k: int,
    corpus_version: str,
) -> str:
    return stable_hash(
        {
            "type": "compression",
            "query": normalized_query,
            "reranked_ids": reranked_ids,
            "compressor_version": compressor_version,
            "top_k": top_k,
            "corpus_version": corpus_version,
        }
    )


def answer_cache_key(
    normalized_query: str,
    context_hash: str,
    generator_version: str,
    corpus_version: str,
) -> str:
    return stable_hash(
        {
            "type": "answer",
            "query": normalized_query,
            "context_hash": context_hash,
            "generator_version": generator_version,
            "corpus_version": corpus_version,
        }
    )