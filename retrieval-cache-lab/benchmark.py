from __future__ import annotations

import asyncio
import statistics
from dataclasses import dataclass
from typing import Any, Dict, List

from answer import OllamaGeneratorAdapter
from compress import ExtractiveCompressorAdapter
from config import Settings
from dedupe import FinalContextDedupe
from doc_store import RedisDocumentStoreAdapter
from embeddings import HFEmbedderAdapter
from memory import SessionMemory
from pipeline import RetrievalPipeline
from redis_client import build_redis_client
from rerank import CrossEncoderRerankerAdapter
from scenarios import ScenarioQuery, all_lab_9_scenarios


@dataclass
class QueryRunResult:
    mode: str
    session_id: str
    label: str
    query: str
    answer: str
    corpus_version: str
    source_class: str
    strict_freshness: bool
    prompt_tokens: int
    ttft_ms: float
    total_latency_ms: float
    compression_ratio: float
    reranked_count: int
    deduped_count: int
    duplicate_reduction_rate: float
    cluster_coverage: int
    cache_stats: Dict[str, int]
    correctness_score: float


def simple_answer_nonempty_score(answer: str) -> float:
    return 1.0 if answer.strip() else 0.0


def sum_cache_stats(rows: List[QueryRunResult]) -> Dict[str, int]:
    totals: Dict[str, int] = {}
    for row in rows:
        for k, v in row.cache_stats.items():
            totals[k] = totals.get(k, 0) + int(v)
    return totals


def safe_mean(values: List[float]) -> float:
    return statistics.mean(values) if values else 0.0


def group_by_label(rows: List[QueryRunResult]) -> Dict[str, List[QueryRunResult]]:
    grouped: Dict[str, List[QueryRunResult]] = {}
    for row in rows:
        grouped.setdefault(row.label, []).append(row)
    return grouped


def print_run_table(rows: List[QueryRunResult]) -> None:
    columns = [
        "mode",
        "session_id",
        "label",
        "query",
        "corpus_version",
        "source_class",
        "strict_freshness",
        "prompt_tokens",
        "compression_ratio",
        "duplicate_reduction_rate",
        "cluster_coverage",
        "ttft_ms",
        "total_latency_ms",
    ]

    data_rows = []
    for row in rows:
        data_rows.append(
            [
                row.mode,
                row.session_id,
                row.label,
                row.query,
                row.corpus_version,
                row.source_class,
                row.strict_freshness,
                row.prompt_tokens,
                round(row.compression_ratio, 4),
                round(row.duplicate_reduction_rate, 4),
                row.cluster_coverage,
                round(row.ttft_ms, 2),
                round(row.total_latency_ms, 2),
            ]
        )

    widths = []
    for i, col in enumerate(columns):
        max_len = len(col)
        for r in data_rows:
            max_len = max(max_len, len(str(r[i])))
        widths.append(max_len)

    def fmt(r: List[Any]) -> str:
        return " | ".join(str(v).ljust(widths[i]) for i, v in enumerate(r))

    print(fmt(columns))
    print("-+-".join("-" * w for w in widths))
    for r in data_rows:
        print(fmt(r))


def print_summary(title: str, rows: List[QueryRunResult]) -> None:
    avg_ttft = safe_mean([r.ttft_ms for r in rows])
    avg_total = safe_mean([r.total_latency_ms for r in rows])
    avg_tokens = safe_mean([r.prompt_tokens for r in rows])

    print(f"\n{title}")
    print(f"count={len(rows)}")
    print(f"avg_ttft_ms={avg_ttft:.2f}")
    print(f"avg_total_latency_ms={avg_total:.2f}")
    print(f"avg_prompt_tokens={avg_tokens:.2f}")

    cache_totals = sum_cache_stats(rows)
    if cache_totals:
        print("cache_totals=", cache_totals)


def print_freshness_summary(rows: List[QueryRunResult]) -> None:
    totals = sum_cache_stats(rows)
    keys = [
        "expiry_misses",
        "stale_evidence_reuse_count",
        "stale_answer_reuse_count",
        "avoidable_recomputes",
    ]
    print("\nFreshness metrics")
    for key in keys:
        print(f"{key}={totals.get(key, 0)}")


def print_redundancy_summary(rows: List[QueryRunResult]) -> None:
    print("\nRedundancy metrics")
    print(
        f"avg_duplicate_reduction_rate={safe_mean([r.duplicate_reduction_rate for r in rows]):.4f}"
    )
    print(
        f"avg_cluster_coverage={safe_mean([float(r.cluster_coverage) for r in rows]):.2f}"
    )
    print(
        f"avg_compression_ratio={safe_mean([r.compression_ratio for r in rows]):.4f}"
    )


def print_comparison(
    baseline_rows: List[QueryRunResult], cached_rows: List[QueryRunResult]
) -> None:
    base_avg = safe_mean([r.total_latency_ms for r in baseline_rows])
    cache_avg = safe_mean([r.total_latency_ms for r in cached_rows])
    speedup = (base_avg / cache_avg) if cache_avg > 0 else 0.0

    base_ttft = safe_mean([r.ttft_ms for r in baseline_rows])
    cache_ttft = safe_mean([r.ttft_ms for r in cached_rows])
    ttft_speedup = (base_ttft / cache_ttft) if cache_ttft > 0 else 0.0

    print("\nOverall comparison")
    print(f"baseline_avg_total_latency_ms={base_avg:.2f}")
    print(f"cached_avg_total_latency_ms={cache_avg:.2f}")
    print(f"overall_speedup={speedup:.2f}x")
    print(f"baseline_avg_ttft_ms={base_ttft:.2f}")
    print(f"cached_avg_ttft_ms={cache_ttft:.2f}")
    print(f"ttft_speedup={ttft_speedup:.2f}x")

    base_by_label = group_by_label(baseline_rows)
    cache_by_label = group_by_label(cached_rows)

    print("\nPer-scenario comparison")
    labels = sorted(set(base_by_label.keys()) | set(cache_by_label.keys()))
    for label in labels:
        b = base_by_label.get(label, [])
        c = cache_by_label.get(label, [])
        b_avg = safe_mean([r.total_latency_ms for r in b])
        c_avg = safe_mean([r.total_latency_ms for r in c])
        s = (b_avg / c_avg) if c_avg > 0 else 0.0
        print(f"{label}: baseline={b_avg:.2f} ms, cached={c_avg:.2f} ms, speedup={s:.2f}x")


async def run_baseline_benchmark(
    settings: Settings,
    scenarios: List[ScenarioQuery],
) -> List[QueryRunResult]:
    embedder = HFEmbedderAdapter(model_name=settings.embedding_model)
    redis_client = build_redis_client(settings)
    session_memories: Dict[str, SessionMemory] = {}

    doc_store = RedisDocumentStoreAdapter(
        redis_client=redis_client,
        index_name=settings.doc_index_name,
        embedding_model=settings.embedding_model,
    )
    reranker = CrossEncoderRerankerAdapter(model_name=settings.reranker_model)
    compressor = ExtractiveCompressorAdapter(
        embedding_model=settings.embedding_model,
        sentences_per_chunk=settings.compressor_sentences_per_chunk,
        min_sentence_chars=settings.compressor_min_sentence_chars,
    )
    generator = OllamaGeneratorAdapter(
        model_name=settings.generator_model,
        base_url=settings.ollama_base_url,
        temperature=settings.generator_temperature,
    )
    final_context_dedupe = FinalContextDedupe(
        embedding_model=settings.embedding_model,
        threshold=0.94,
    )

    rows: List[QueryRunResult] = []

    for item in scenarios:
        if item.session_id not in session_memories:
            session_memories[item.session_id] = SessionMemory(
                settings=settings,
                redis_client=redis_client,
                session_id=item.session_id,
            )

        pipeline = RetrievalPipeline(
            session_memory=session_memories[item.session_id],
            embedder=embedder,
            doc_store=doc_store,
            reranker=reranker,
            compressor=compressor,
            generator=generator,
            retrieve_top_k=settings.retrieve_top_k,
            rerank_top_k=settings.rerank_top_k,
            compress_top_k=settings.compress_top_k,
            final_context_dedupe=final_context_dedupe,
        )

        result = await pipeline.run_baseline(item.query)
        correctness_score = simple_answer_nonempty_score(result.answer)

        rows.append(
            QueryRunResult(
                mode="baseline",
                session_id=item.session_id,
                label=item.label,
                query=item.query,
                answer=result.answer,
                corpus_version=getattr(item, "corpus_version", "docs_v1"),
                source_class=getattr(item, "source_class", "stable"),
                strict_freshness=True,
                prompt_tokens=result.prompt_tokens,
                ttft_ms=result.ttft_ms,
                total_latency_ms=result.total_latency_ms,
                compression_ratio=result.compression_ratio,
                reranked_count=result.reranked_count,
                deduped_count=result.deduped_count,
                duplicate_reduction_rate=result.duplicate_reduction_rate,
                cluster_coverage=result.cluster_coverage,
                cache_stats=result.cache_stats,
                correctness_score=correctness_score,
            )
        )

    return rows


async def run_cached_benchmark(
    settings: Settings,
    scenarios: List[ScenarioQuery],
    strict_freshness: bool,
    mode_name: str,
) -> List[QueryRunResult]:
    embedder = HFEmbedderAdapter(model_name=settings.embedding_model)
    redis_client = build_redis_client(settings)
    session_memories: Dict[str, SessionMemory] = {}

    doc_store = RedisDocumentStoreAdapter(
        redis_client=redis_client,
        index_name=settings.doc_index_name,
        embedding_model=settings.embedding_model,
    )
    reranker = CrossEncoderRerankerAdapter(model_name=settings.reranker_model)
    compressor = ExtractiveCompressorAdapter(
        embedding_model=settings.embedding_model,
        sentences_per_chunk=settings.compressor_sentences_per_chunk,
        min_sentence_chars=settings.compressor_min_sentence_chars,
    )
    generator = OllamaGeneratorAdapter(
        model_name=settings.generator_model,
        base_url=settings.ollama_base_url,
        temperature=settings.generator_temperature,
    )
    final_context_dedupe = FinalContextDedupe(
        embedding_model=settings.embedding_model,
        threshold=0.94,
    )

    rows: List[QueryRunResult] = []

    for item in scenarios:
        if item.session_id not in session_memories:
            session_memories[item.session_id] = SessionMemory(
                settings=settings,
                redis_client=redis_client,
                session_id=item.session_id,
            )

        pipeline = RetrievalPipeline(
            session_memory=session_memories[item.session_id],
            embedder=embedder,
            doc_store=doc_store,
            reranker=reranker,
            compressor=compressor,
            generator=generator,
            retrieve_top_k=settings.retrieve_top_k,
            rerank_top_k=settings.rerank_top_k,
            compress_top_k=settings.compress_top_k,
            final_context_dedupe=final_context_dedupe,
        )

        result = await pipeline.run_cached(
            query=item.query,
            redis_client=redis_client,
            corpus_version=getattr(item, "corpus_version", "docs_v1"),
            embedding_model=settings.embedding_model,
            reranker_model=settings.reranker_model,
            compressor_version="compress_v1",
            generator_version="gen_v1",
            source_class=getattr(item, "source_class", "stable"),
            strict_freshness=strict_freshness,
        )
        correctness_score = simple_answer_nonempty_score(result.answer)

        rows.append(
            QueryRunResult(
                mode=mode_name,
                session_id=item.session_id,
                label=item.label,
                query=item.query,
                answer=result.answer,
                corpus_version=getattr(item, "corpus_version", "docs_v1"),
                source_class=getattr(item, "source_class", "stable"),
                strict_freshness=strict_freshness,
                prompt_tokens=result.prompt_tokens,
                ttft_ms=result.ttft_ms,
                total_latency_ms=result.total_latency_ms,
                compression_ratio=result.compression_ratio,
                reranked_count=result.reranked_count,
                deduped_count=result.deduped_count,
                duplicate_reduction_rate=result.duplicate_reduction_rate,
                cluster_coverage=result.cluster_coverage,
                cache_stats=result.cache_stats,
                correctness_score=correctness_score,
            )
        )

    return rows


def delete_prefix(redis_client, prefix: str) -> int:
    count = 0
    cursor = 0
    pattern = f"{prefix}:*"
    while True:
        cursor, keys = redis_client.scan(cursor=cursor, match=pattern, count=500)
        if keys:
            redis_client.delete(*keys)
            count += len(keys)
        if cursor == 0:
            break
    return count


async def main() -> None:
    settings = Settings()
    scenarios = all_lab_9_scenarios()

    print("Running Lab 9A baseline...")
    baseline_rows = await run_baseline_benchmark(settings, scenarios)

    redis_client = build_redis_client(settings)
    delete_prefix(redis_client, "lab9")

    print("\nRunning Lab 9B/9C cached safe...")
    cached_safe_rows = await run_cached_benchmark(
        settings,
        scenarios,
        strict_freshness=True,
        mode_name="cached_safe",
    )

    delete_prefix(redis_client, "lab9")

    print("\nRunning Lab 9C cached unsafe...")
    cached_unsafe_rows = await run_cached_benchmark(
        settings,
        scenarios,
        strict_freshness=False,
        mode_name="cached_unsafe",
    )

    print("\nBaseline runs")
    print_run_table(baseline_rows)
    print_summary("Baseline summary", baseline_rows)
    print_redundancy_summary(baseline_rows)

    print("\nCached safe runs")
    print_run_table(cached_safe_rows)
    print_summary("Cached safe summary", cached_safe_rows)
    print_freshness_summary(cached_safe_rows)
    print_redundancy_summary(cached_safe_rows)

    print("\nCached unsafe runs")
    print_run_table(cached_unsafe_rows)
    print_summary("Cached unsafe summary", cached_unsafe_rows)
    print_freshness_summary(cached_unsafe_rows)
    print_redundancy_summary(cached_unsafe_rows)

    print_comparison(baseline_rows, cached_safe_rows)
    delete_prefix(redis_client, "lab9")


if __name__ == "__main__":
    asyncio.run(main())