# Retrieval Cache Lab

This lab turns retrieval optimization into something measurable.

It compares a plain retrieval pipeline against a cache-aware pipeline that adds:

- exact caching for expensive retrieval stages
- freshness controls with TTL and corpus-version scoping
- semantic deduplication before final context assembly
- session memory that influences prompt construction

The practical question behind the lab is:

**Can we speed up retrieval-heavy question answering without reusing stale evidence or bloating the final prompt with redundant chunks?**

## What This Lab Covers

- document chunking and ingestion into Redis
- local embedding-based retrieval
- cross-encoder reranking
- extractive compression
- answer generation through Ollama
- exact cache layers for embedding, retrieval, rerank, compression, and answer generation
- freshness-aware cache keys using `corpus_version`
- different TTLs for `stable`, `semi_stable`, and `unstable` source classes
- final-context semantic dedupe to remove near-duplicate evidence
- benchmark scenarios for reuse, freshness, and redundancy

## Architecture

The pipeline is implemented in [pipeline.py](./retrieval-cache-lab/pipeline.py) and can run in two modes:

- `run_baseline()`: recomputes every stage
- `run_cached()`: wraps the expensive stages with Redis-backed exact caches

High-level flow:

```text
query
  -> normalize
  -> retrieve recent + semantic session context
  -> embed query
  -> retrieve top-k document chunks
  -> rerank
  -> final-context dedupe
  -> compress
  -> answer
  -> log timing, token, cache, and redundancy metrics
```

The benchmark in [benchmark.py](./retrieval-cache-lab/benchmark.py) runs three modes:

- `baseline`
- `cached_safe`
- `cached_unsafe`

`cached_safe` includes `corpus_version` in cache keys. `cached_unsafe` intentionally relaxes freshness constraints so you can see where stale reuse starts to appear.

## Project Files

Core pipeline and orchestration:

- [pipeline.py](./retrieval-cache-lab/pipeline.py): baseline and cached retrieval pipeline
- [benchmark.py](./retrieval-cache-lab/benchmark.py): runs the full benchmark suite and prints summaries
- [config.py](./retrieval-cache-lab/config.py): local settings for Redis, models, retrieval sizes, and Ollama

Retrieval and answer stages:

- [chunking.py](./retrieval-cache-lab/chunking.py): simple overlapping text chunker
- [ingest.py](./retrieval-cache-lab/ingest.py): ingests `sample_doc.txt` or another text file into Redis
- [doc_store.py](./retrieval-cache-lab/doc_store.py): stores chunks and performs cosine-similarity retrieval
- [rerank.py](./retrieval-cache-lab/rerank.py): reranks retrieved chunks with `BAAI/bge-reranker-base`
- [compress.py](./retrieval-cache-lab/compress.py): extractive compression using sentence-level similarity
- [answer.py](./retrieval-cache-lab/answer.py): builds the final grounded prompt and calls Ollama
- [memory.py](./retrieval-cache-lab/memory.py): recent history plus RedisVL-backed semantic message history

Cache and reuse logic:

- [cache_wrappers.py](./retrieval-cache-lab/cache_wrappers.py): cache-aware wrappers for each expensive stage
- [cache_store.py](./retrieval-cache-lab/cache_store.py): exact Redis cache plus cache stats
- [cache_keys.py](./retrieval-cache-lab/cache_keys.py): deterministic key construction
- [cache_policy.py](./retrieval-cache-lab/cache_policy.py): per-layer TTL policy
- [dedupe.py](./retrieval-cache-lab/dedupe.py): semantic dedupe for the final context window
- [normalize.py](./retrieval-cache-lab/normalize.py): query normalization used before caching

Scenario definitions:

- [scenarios.py](./retrieval-cache-lab/scenarios.py): main reuse and freshness scenarios
- [scenarios_freshness.py](./retrieval-cache-lab/scenarios_freshness.py): freshness-only scenario helpers
- [sample_doc.txt](./retrieval-cache-lab/sample_doc.txt): starter source document for ingestion

## Cache Layers In This Lab

The cached pipeline currently implements exact caches for these stages:

| Layer | Key Inputs | Why It Helps | Freshness Guard |
|---|---|---|---|
| Embedding | normalized query, embedding model | avoids repeated embedding work | long TTL tied to model version |
| Retrieval | normalized query, `top_k`, embedding model, optionally `corpus_version` | avoids repeated vector search | TTL plus corpus-version scoping |
| Rerank | normalized query, candidate ids, reranker model, optionally `corpus_version` | skips expensive reranker passes | TTL plus corpus-version scoping |
| Compression | normalized query, reranked ids, compressor version, optionally `corpus_version` | avoids repeated context compression | TTL plus corpus-version scoping |
| Answer | normalized query, context hash, generator version, optionally `corpus_version` | skips repeated generation | shortest TTLs for changing sources |

There is no semantic answer cache in the current implementation. This lab stays focused on exact reuse, freshness safety, and redundancy control inside the retrieval pipeline.

## Freshness Model

Freshness is handled in two ways:

1. `corpus_version` is included in cache keys when `strict_freshness=True`.
2. TTLs vary by source stability class in [cache_policy.py](./retrieval-cache-lab/cache_policy.py).

Current defaults:

- embeddings: `86400s`
- retrieval: `3600s` stable, `900s` semi-stable, `120s` unstable
- rerank: `1800s` stable, `600s` semi-stable, `120s` unstable
- compression: `1800s` stable, `600s` semi-stable, `120s` unstable
- answer: `900s` stable, `300s` semi-stable, `60s` unstable

The code also exposes freshness counters like:

- `stale_evidence_reuse_count`
- `stale_answer_reuse_count`
- `expiry_misses`
- `avoidable_recomputes`

## Redundancy Control

This lab includes semantic dedupe before compression and prompt assembly.

[dedupe.py](./retrieval-cache-lab/dedupe.py) embeds the reranked chunks and drops near-duplicates above a similarity threshold. That helps the benchmark measure:

- `duplicate_reduction_rate`
- `cluster_coverage`
- `compression_ratio`
- approximate prompt-size reduction

The document store also includes an `add_chunks_deduped()` path in [doc_store.py](./retrieval-cache-lab/doc_store.py), which is useful if you want to extend this lab into ingestion-time dedupe later.

## Benchmark Scenarios

The default benchmark run uses the reuse-oriented scenario set from [scenarios.py](./retrieval-cache-lab/scenarios.py):

- exact repeated queries
- same-session repeated questions after a short pause
- repeated popular questions across different sessions
- session-local repeated themes

This gives you two main kinds of signal:

- reuse value
- redundancy reduction

Freshness scenario helpers for document updates and corpus-version changes are also defined in [scenarios.py](./retrieval-cache-lab/scenarios.py) and [scenarios_freshness.py](./retrieval-cache-lab/scenarios_freshness.py), but they are not part of the default `benchmark.py` run unless you switch the scenario loader.

## Requirements

- Python `3.12+`
- Redis running on `redis://localhost:6379`
- Ollama running on `http://localhost:11434`
- model access for:
  - `sentence-transformers/all-MiniLM-L6-v2`
  - `BAAI/bge-reranker-base`
  - `llama3.1:8b` in Ollama

Install the Ollama model if needed:

```bash
ollama pull llama3.1:8b
```

Start Redis quickly with Docker if you do not already have it:

```bash
docker run --name retrieval-cache-lab -p 6379:6379 -d redis:8
```

## Setup

Run everything from inside this directory:

```bash
cd ./retrieval-cache-lab
uv sync
```

## Ingest Sample Data

The lab ships with [sample_doc.txt](./retrieval-cache-lab/sample_doc.txt). Ingest it with:

```bash
uv run python ingest.py
```

To ingest a different file, update the call in [ingest.py](./retrieval-cache-lab/ingest.py) or import `ingest_text_file()` from your own script.

## Run The Benchmark

```bash
uv run python benchmark.py
```

The benchmark:

- runs the baseline pipeline
- clears the `lab9:*` Redis cache keys
- runs the freshness-safe cached pipeline
- clears the cache again
- runs the freshness-unsafe cached pipeline
- prints per-run tables and summary metrics

If you want the benchmark to exercise freshness counters meaningfully, change the scenario source in [benchmark.py](./retrieval-cache-lab/benchmark.py) from `all_lab_9_scenarios()` to `all_lab_9_with_freshness_scenarios()`.

## How To Read The Output

The most useful comparisons are:

- `overall_speedup`: end-to-end latency gain from caching
- `ttft_speedup`: improvement in answer start time
- cache totals by layer: where reuse is actually happening
- freshness counters: whether unsafe reuse appears when you include version-change scenarios
- redundancy metrics: whether dedupe reduces duplicate context without collapsing useful coverage

If `cached_safe` is faster than `baseline` without increasing stale reuse counts, the lab is doing its job.

If `cached_unsafe` is faster than `cached_safe` but increases stale reuse counters, that is the intended lesson: speed without freshness controls can be misleading.

## Suggested Learning Order

1. Ingest the sample document and run the benchmark once.
2. Inspect [cache_wrappers.py](./retrieval-cache-lab/cache_wrappers.py) to see how each stage gets wrapped.
3. Tweak TTLs in [cache_policy.py](./retrieval-cache-lab/cache_policy.py) and rerun.
4. Change `corpus_version` in the scenarios to watch freshness behavior.
5. Raise or lower the dedupe threshold in [dedupe.py](./retrieval-cache-lab/dedupe.py) and compare redundancy metrics.

## Where This Fits In The Repo

This lab is the retrieval-optimization branch of the broader roadmap in the root [README.md](./README.md). It builds on the earlier caching labs by moving from:

- prompt reuse
- exact answer reuse
- semantic answer reuse
- conversation state reuse

into retrieval-stage reuse, freshness control, and context-quality optimization.

## Baseline runs

| mode | session_id | label | query | corpus_version | source_class | strict_freshness | prompt_tokens | compression_ratio | duplicate_reduction_rate | cluster_coverage | ttft_ms | total_latency_ms |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| baseline | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 8387.60 | 9474.33 |
| baseline | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 2054.81 | 2879.90 |
| baseline | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 1774.04 | 2685.60 |
| baseline | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | True | 683 | 0.7887 | 0.0 | 0 | 4921.19 | 5671.19 |
| baseline | s_pause_1 | short_pause | What did you say about the refund policy for annual subscriptions? | docs_v1 | semi_stable | True | 669 | 0.7555 | 0.0 | 0 | 4020.40 | 4979.10 |
| baseline | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | True | 683 | 0.7887 | 0.0 | 0 | 3872.46 | 4727.38 |
| baseline | s_pop_1 | popular | How do I reset my password? | docs_v1 | stable | True | 906 | 0.7201 | 0.0 | 0 | 6878.66 | 7672.20 |
| baseline | s_pop_2 | popular | How do I reset my password? | docs_v1 | stable | True | 793 | 0.7201 | 0.0 | 0 | 5155.09 | 5943.64 |
| baseline | s_pop_3 | popular | How do I reset my password? | docs_v1 | stable | True | 786 | 0.7201 | 0.0 | 0 | 5797.48 | 6480.65 |
| baseline | s_pop_1 | popular | Where can I download my invoice? | docs_v1 | stable | True | 841 | 0.6367 | 0.0 | 0 | 6798.18 | 7685.18 |
| baseline | s_pop_2 | popular | Where can I download my invoice? | docs_v1 | stable | True | 747 | 0.6367 | 0.0 | 0 | 4793.83 | 5592.13 |
| baseline | s_pop_3 | popular | Where can I download my invoice? | docs_v1 | stable | True | 740 | 0.6367 | 0.0 | 0 | 4850.49 | 5736.36 |
| baseline | s_theme_1 | theme | What is the notice period? | docs_v1 | stable | True | 659 | 0.5971 | 0.0 | 0 | 4866.86 | 5580.40 |
| baseline | s_theme_1 | theme | What is the termination notice period? | docs_v1 | stable | True | 653 | 0.5971 | 0.0 | 0 | 4119.22 | 4882.15 |
| baseline | s_theme_1 | theme | What is the probation notice period? | docs_v1 | stable | True | 654 | 0.5971 | 0.0 | 0 | 4382.32 | 5253.52 |
| baseline | s_theme_1 | theme | Compare probation and termination notice periods. | docs_v1 | stable | True | 658 | 0.6197 | 0.0 | 0 | 4280.99 | 5147.72 |

### Baseline summary

- **count:** 16
- **avg_ttft_ms:** 4809.60
- **avg_total_latency_ms:** 5649.46
- **avg_prompt_tokens:** 711.06

### Redundancy metrics

- **avg_duplicate_reduction_rate:** 0.0000
- **avg_cluster_coverage:** 0.00
- **avg_compression_ratio:** 0.6629

---

## Cached safe runs

| mode | session_id | label | query | corpus_version | source_class | strict_freshness | prompt_tokens | compression_ratio | duplicate_reduction_rate | cluster_coverage | ttft_ms | total_latency_ms |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| cached_safe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 6074.95 | 6396.51 |
| cached_safe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 0.87 | 78.66 |
| cached_safe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | True | 635 | 0.5971 | 0.0 | 0 | 0.55 | 31.21 |
| cached_safe | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | True | 683 | 0.7887 | 0.0 | 0 | 4415.30 | 5120.70 |
| cached_safe | s_pause_1 | short_pause | What did you say about the refund policy for annual subscriptions? | docs_v1 | semi_stable | True | 669 | 0.7555 | 0.0 | 0 | 4118.70 | 5089.95 |
| cached_safe | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | True | 683 | 0.7887 | 0.0 | 0 | 3493.19 | 4034.83 |
| cached_safe | s_pop_1 | popular | How do I reset my password? | docs_v1 | stable | True | 906 | 0.7201 | 0.0 | 0 | 6569.69 | 7365.89 |
| cached_safe | s_pop_2 | popular | How do I reset my password? | docs_v1 | stable | True | 793 | 0.7201 | 0.0 | 0 | 5283.02 | 5802.13 |
| cached_safe | s_pop_3 | popular | How do I reset my password? | docs_v1 | stable | True | 786 | 0.7201 | 0.0 | 0 | 5207.94 | 5688.22 |
| cached_safe | s_pop_1 | popular | Where can I download my invoice? | docs_v1 | stable | True | 841 | 0.6367 | 0.0 | 0 | 7106.91 | 7970.67 |
| cached_safe | s_pop_2 | popular | Where can I download my invoice? | docs_v1 | stable | True | 747 | 0.6367 | 0.0 | 0 | 5529.86 | 6092.75 |
| cached_safe | s_pop_3 | popular | Where can I download my invoice? | docs_v1 | stable | True | 740 | 0.6367 | 0.0 | 0 | 7812.16 | 8783.21 |
| cached_safe | s_theme_1 | theme | What is the notice period? | docs_v1 | stable | True | 659 | 0.5971 | 0.0 | 0 | 6545.09 | 8788.94 |
| cached_safe | s_theme_1 | theme | What is the termination notice period? | docs_v1 | stable | True | 653 | 0.5971 | 0.0 | 0 | 4099.27 | 4701.79 |
| cached_safe | s_theme_1 | theme | What is the probation notice period? | docs_v1 | stable | True | 654 | 0.5971 | 0.0 | 0 | 4034.95 | 4892.34 |
| cached_safe | s_theme_1 | theme | Compare probation and termination notice periods. | docs_v1 | stable | True | 658 | 0.6197 | 0.0 | 0 | 4479.45 | 5390.35 |

### Cached safe summary

- **count:** 16
- **avg_ttft_ms:** 4673.24
- **avg_total_latency_ms:** 5389.26
- **avg_prompt_tokens:** 711.06

### Cache totals

- **embedding_hits:** 8
- **embedding_misses:** 8
- **retrieval_hits:** 8
- **retrieval_misses:** 8
- **rerank_hits:** 8
- **rerank_misses:** 8
- **compression_hits:** 8
- **compression_misses:** 8
- **answer_hits:** 2
- **answer_misses:** 14
- **expiry_misses:** 0
- **stale_evidence_reuse_count:** 0
- **stale_answer_reuse_count:** 0
- **avoidable_recomputes:** 0

### Freshness metrics

- **expiry_misses:** 0
- **stale_evidence_reuse_count:** 0
- **stale_answer_reuse_count:** 0
- **avoidable_recomputes:** 0

### Redundancy metrics

- **avg_duplicate_reduction_rate:** 0.0000
- **avg_cluster_coverage:** 0.00
- **avg_compression_ratio:** 0.6629

---

## Cached unsafe runs

| mode | session_id | label | query | corpus_version | source_class | strict_freshness | prompt_tokens | compression_ratio | duplicate_reduction_rate | cluster_coverage | ttft_ms | total_latency_ms |
|---|---|---|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| cached_unsafe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | False | 635 | 0.5971 | 0.0 | 0 | 6647.24 | 6877.35 |
| cached_unsafe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | False | 635 | 0.5971 | 0.0 | 0 | 0.89 | 75.61 |
| cached_unsafe | s_exact_1 | exact_repeat | What is the termination notice period? | docs_v1 | stable | False | 635 | 0.5971 | 0.0 | 0 | 2.20 | 33.81 |
| cached_unsafe | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | False | 683 | 0.7887 | 0.0 | 0 | 4791.53 | 5475.99 |
| cached_unsafe | s_pause_1 | short_pause | What did you say about the refund policy for annual subscriptions? | docs_v1 | semi_stable | False | 669 | 0.7555 | 0.0 | 0 | 3917.56 | 4876.67 |
| cached_unsafe | s_pause_1 | short_pause | Explain the refund policy for annual subscriptions. | docs_v1 | semi_stable | False | 683 | 0.7887 | 0.0 | 0 | 0.88 | 607.35 |
| cached_unsafe | s_pop_1 | popular | How do I reset my password? | docs_v1 | stable | False | 906 | 0.7201 | 0.0 | 0 | 7647.94 | 8328.87 |
| cached_unsafe | s_pop_2 | popular | How do I reset my password? | docs_v1 | stable | False | 793 | 0.7201 | 0.0 | 0 | 0.59 | 698.70 |
| cached_unsafe | s_pop_3 | popular | How do I reset my password? | docs_v1 | stable | False | 786 | 0.7201 | 0.0 | 0 | 0.95 | 326.82 |
| cached_unsafe | s_pop_1 | popular | Where can I download my invoice? | docs_v1 | stable | False | 841 | 0.6367 | 0.0 | 0 | 8713.65 | 9084.53 |
| cached_unsafe | s_pop_2 | popular | Where can I download my invoice? | docs_v1 | stable | False | 772 | 0.6367 | 0.0 | 0 | 1.54 | 622.96 |
| cached_unsafe | s_pop_3 | popular | Where can I download my invoice? | docs_v1 | stable | False | 767 | 0.6367 | 0.0 | 0 | 1.14 | 30.69 |
| cached_unsafe | s_theme_1 | theme | What is the notice period? | docs_v1 | stable | False | 659 | 0.5971 | 0.0 | 0 | 5549.40 | 6320.23 |
| cached_unsafe | s_theme_1 | theme | What is the termination notice period? | docs_v1 | stable | False | 653 | 0.5971 | 0.0 | 0 | 1.06 | 610.69 |
| cached_unsafe | s_theme_1 | theme | What is the probation notice period? | docs_v1 | stable | False | 645 | 0.5971 | 0.0 | 0 | 4201.69 | 4482.08 |
| cached_unsafe | s_theme_1 | theme | Compare probation and termination notice periods. | docs_v1 | stable | False | 648 | 0.6197 | 0.0 | 0 | 4406.94 | 5277.18 |

### Cached unsafe summary

- **count:** 16
- **avg_ttft_ms:** 2867.83
- **avg_total_latency_ms:** 3358.09
- **avg_prompt_tokens:** 713.12

### Cache totals

- **embedding_hits:** 8
- **embedding_misses:** 8
- **retrieval_hits:** 8
- **retrieval_misses:** 8
- **rerank_hits:** 8
- **rerank_misses:** 8
- **compression_hits:** 8
- **compression_misses:** 8
- **answer_hits:** 8
- **answer_misses:** 8
- **expiry_misses:** 0
- **stale_evidence_reuse_count:** 0
- **stale_answer_reuse_count:** 0
- **avoidable_recomputes:** 0

### Freshness metrics

- **expiry_misses:** 0
- **stale_evidence_reuse_count:** 0
- **stale_answer_reuse_count:** 0
- **avoidable_recomputes:** 0

### Redundancy metrics

- **avg_duplicate_reduction_rate:** 0.0000
- **avg_cluster_coverage:** 0.00
- **avg_compression_ratio:** 0.6629

---

## Overall comparison

- **baseline_avg_total_latency_ms:** 5649.46
- **cached_avg_total_latency_ms:** 5389.26
- **overall_speedup:** 1.05x
- **baseline_avg_ttft_ms:** 4809.60
- **cached_avg_ttft_ms:** 4673.24
- **ttft_speedup:** 1.03x

## Per-scenario comparison

- **exact_repeat:** baseline=5013.27 ms, cached=2168.79 ms, speedup=2.31x
- **popular:** baseline=6518.36 ms, cached=6950.48 ms, speedup=0.94x
- **short_pause:** baseline=5125.89 ms, cached=4748.49 ms, speedup=1.08x


## Benchmark results

We evaluated three modes:

- **baseline**: no cache reuse
- **cached_safe**: cache enabled with strict freshness guarantees
- **cached_unsafe**: cache enabled with answer reuse allowed more aggressively

## Headline results

| Metric | Baseline | Cached Safe | Cached Unsafe |
|---|---:|---:|---:|
| Avg TTFT (ms) | 4809.60 | 4673.24 | 2867.83 |
| Avg Total Latency (ms) | 5649.46 | 5389.26 | 3358.09 |
| Avg Prompt Tokens | 711.06 | 711.06 | 713.12 |

### Speedups vs baseline

| Comparison | Total Latency Speedup | TTFT Speedup |
|---|---:|---:|
| Cached Safe vs Baseline | 1.05x | 1.03x |
| Cached Unsafe vs Baseline | 1.68x | 1.68x |

## Scenario-level results

| Scenario | Baseline (ms) | Cached Safe (ms) | Speedup |
|---|---:|---:|---:|
| exact_repeat | 5013.27 | 2168.79 | 2.31x |
| popular | 6518.36 | 6950.48 | 0.94x |
| short_pause | 5125.89 | 4748.49 | 1.08x |

## Cache behavior

### Cached Safe
- Embedding hits/misses: **8 / 8**
- Retrieval hits/misses: **8 / 8**
- Rerank hits/misses: **8 / 8**
- Compression hits/misses: **8 / 8**
- Answer hits/misses: **2 / 14**

### Cached Unsafe
- Embedding hits/misses: **8 / 8**
- Retrieval hits/misses: **8 / 8**
- Rerank hits/misses: **8 / 8**
- Compression hits/misses: **8 / 8**
- Answer hits/misses: **8 / 8**

## Freshness safety

Both cache modes reported:

- **expiry_misses:** 0
- **stale_evidence_reuse_count:** 0
- **stale_answer_reuse_count:** 0
- **avoidable_recomputes:** 0

## Redundancy metrics

Across all runs:

- **avg_duplicate_reduction_rate:** 0.0000
- **avg_cluster_coverage:** 0.00
- **avg_compression_ratio:** 0.6629

## Interpretation

- **Cached safe** delivered only a modest overall improvement, but gave a strong **2.31x speedup** for exact repeats.
- **Cached unsafe** achieved much larger latency wins by reusing final answers more aggressively.
- **Popular-query performance** did not improve under safe caching, suggesting cross-session reuse is still limited or overshadowed by other stages.
- Redundancy metrics remained flat, indicating this experiment isolates cache reuse rather than deduplication or clustering gains.