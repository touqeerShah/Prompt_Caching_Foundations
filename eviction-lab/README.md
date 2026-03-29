# Eviction Lab

Eviction is where cache design stops being abstract and starts becoming operational.

This lab is meant to be read like a lecture and used like a blog-style walkthrough. The goal is not just to memorize `TTL`, `LRU`, `LFU`, `FIFO`, and semantic-aware eviction. The goal is to understand what problem each policy solves, what it does not solve, and how to benchmark the tradeoffs in a controlled way.

The central idea of this lab is:

- `TTL` solves freshness
- `LRU`, `LFU`, and `FIFO` solve capacity pressure
- semantic-aware eviction solves redundancy and diversity in retrieval-oriented memory

So you should not compare them as if they solve the same problem. In real systems, the common pattern is:

- use `TTL` as the outer freshness filter
- then use one capacity policy when the cache is full

That is the architectural lens for the entire lab.

## Why This Lab Matters for LLM Systems

In LLM applications, eviction decisions change behavior directly:

- too-short TTL causes avoidable misses and recompute
- too-long TTL causes stale answers or stale context reuse
- weak capacity policies evict useful shared assets too early
- non-diversity-aware policies can keep too many near-duplicate chunks in retrieval memory

This lab turns those ideas into measurable experiments.

## The Right Learning Order

### 1. TTL first

TTL is the best first step because it is easy to reason about and immediately useful.

Use TTL for:

- session memory
- temporary tool results
- semantic cache entries
- exact answer cache
- retrieval results from unstable sources

What you learn:

- stale vs fresh tradeoff
- short TTL causing misses
- long TTL causing bad or outdated reuse

### 2. TTL + LRU second

This is the next best step for recent-turn memory and hot working sets.

Use for:

- recent conversation state
- recent retrieval chunks
- exact cache entries for active sessions

What you learn:

- recency bias
- cache thrashing
- hot set stability

### 3. TTL + LFU third

This is best for shared reusable assets.

Use for:

- common prompt templates
- org policy blocks
- frequently reused tool schemas
- common FAQ responses

What you learn:

- popularity vs recency
- preserving globally useful entries
- long-tail prompt pressure

### 4. FIFO fourth

FIFO mainly belongs here as a baseline comparison.

Use for:

- simple queue-like temporary caches
- baseline experiments

What you learn:

- why simple eviction often underperforms for LLM workloads

### 5. Semantic-aware eviction last

This is the advanced stage.

Use for:

- vector retrieval caches
- semantic memory stores
- RAG chunk stores where diversity matters more than raw count

What you learn:

- redundancy pruning
- diversity preservation
- why "most similar to others" can be the best eviction target

## The Big Architectural Rule

When capacity is exceeded, the best default order is:

1. remove expired items first
2. if the cache is still over capacity, apply a capacity policy
3. if semantic-aware mode is enabled, use redundancy-aware selection among eligible items

That means `TTL` is the outer freshness filter, not a competing policy.

## Best Implementation Approach

Build this as one lab with pluggable policies.

The cache should support:

- `put(key, value, metadata)`
- `get(key)`
- `evict_if_needed()`

Each entry should store:

- `key`
- `created_at`
- `last_access_at`
- `access_count`
- `ttl_seconds`
- `size_estimate`
- `semantic_vector` or redundancy score later

## Project Structure

This folder already has the structure for a practical eviction lab:

```text
eviction-lab/
├─ README.md
├─ pyproject.toml
├─ main.py
├─ ttl_lab.py
├─ cache_policies.py
├─ cache_store.py
├─ scenarios.py
├─ scenarios_semantic.py
├─ benchmark_eviction.py
├─ benchmark_eviction_semantic.py
├─ analyze_results.py
└─ vector_utils.py
```

## What Each File Is For

### `ttl_lab.py`

This is the simplest lecture-friendly starting point.

It teaches:

- TTL as freshness control
- stale serve tracking
- expiry miss tracking
- why one global TTL is often the wrong choice

### `cache_store.py`

This is the generic in-memory cache core.

It handles:

- max entries
- TTL support
- stats
- pluggable eviction policy

### `cache_policies.py`

This is where the eviction logic lives.

It should expose:

- TTL expiry helpers
- `LRU`
- `LFU`
- `FIFO`
- semantic-aware eviction

### `scenarios.py`

This holds the non-semantic workload generators:

- active conversation sessions
- shared templates
- long-tail prompts
- stale data patterns
- repeated bursty access patterns

### `scenarios_semantic.py`

This holds semantic memory and duplicate-heavy workloads.

### `benchmark_eviction.py`

This runs structured benchmarks across:

- `TTL + LRU`
- `TTL + LFU`
- `TTL + FIFO`

### `benchmark_eviction_semantic.py`

This extends the benchmark to semantic-aware eviction and tracks diversity-oriented metrics.

## Minimal Code Shape

### `cache_policies.py`

```python
from __future__ import annotations

from typing import Dict, Any


def is_expired(entry: Dict[str, Any], now_ts: float) -> bool:
    ttl = entry.get("ttl_seconds")
    if ttl is None:
        return False
    return (now_ts - entry["created_at"]) > ttl


def select_lru(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(cache.items(), key=lambda kv: kv[1]["last_access_at"])[0]


def select_lfu(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(
        cache.items(),
        key=lambda kv: (kv[1]["access_count"], kv[1]["last_access_at"]),
    )[0]


def select_fifo(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(cache.items(), key=lambda kv: kv[1]["created_at"])[0]
```

### `cache_store.py`

```python
from __future__ import annotations

import time
from typing import Any, Callable, Dict, Optional

from cache_policies import is_expired


class CacheStore:
    def __init__(self, max_entries: int, eviction_selector: Callable):
        self.max_entries = max_entries
        self.eviction_selector = eviction_selector
        self.data: Dict[str, Dict[str, Any]] = {}
        self.stats = {
            "hits": 0,
            "misses": 0,
            "evictions": 0,
            "expired": 0,
            "stale_serves": 0,
        }

    def _now(self) -> float:
        return time.time()

    def _purge_expired(self) -> None:
        now_ts = self._now()
        expired_keys = [k for k, v in self.data.items() if is_expired(v, now_ts)]
        for k in expired_keys:
            del self.data[k]
            self.stats["expired"] += 1

    def get(self, key: str) -> Optional[Any]:
        self._purge_expired()
        entry = self.data.get(key)
        if entry is None:
            self.stats["misses"] += 1
            return None

        entry["last_access_at"] = self._now()
        entry["access_count"] += 1
        self.stats["hits"] += 1
        return entry["value"]

    def put(self, key: str, value: Any, ttl_seconds: int | None = None) -> None:
        self._purge_expired()
        now_ts = self._now()

        self.data[key] = {
            "value": value,
            "created_at": now_ts,
            "last_access_at": now_ts,
            "access_count": 1,
            "ttl_seconds": ttl_seconds,
        }

        while len(self.data) > self.max_entries:
            evict_key = self.eviction_selector(self.data)
            del self.data[evict_key]
            self.stats["evictions"] += 1
```

## Metrics to Track

For every policy, record:

- request count
- hit count
- miss count
- eviction count
- expired entry count
- stale serve count
- hot-item eviction count
- average age of evicted entries
- average access count of evicted entries

For semantic-aware eviction later, also record:

- redundancy score of evicted item
- diversity score of retained set

## Metrics That Matter Most by Policy

### TTL

- stale serve count
- expiry miss count
- hit rate
- average item age at hit

### LRU

- hit rate under bursty recency workloads
- eviction count
- hot-item survival

### LFU

- hit rate under repeated shared-template workloads
- long-tail suppression
- popular-item retention

### FIFO

- hit rate baseline
- shared key eviction behavior
- hot-item eviction behavior

### Semantic-aware

- retrieval diversity
- duplicate reduction
- answer quality downstream

## Practical Weekly Roadmap

### Week 1 — TTL-only

Implement:

- exact cache entries with TTL
- session entries with TTL
- expiry checks on get/put

Run scenarios:

- TTL too short
- TTL too long
- stable vs unstable data

Expected lesson:

- freshness is not free; aggressive TTL kills hit rate

### Week 2 — TTL + LRU

Implement:

- capacity limit
- evict expired first
- then evict least recently used

Run scenarios:

- active session burst
- recent-turn chat
- hot working set

Expected lesson:

- LRU is strong for active chat and state workloads

### Week 3 — TTL + LFU

Implement:

- expire first
- then evict lowest-frequency items

Run scenarios:

- shared system prompts
- common FAQs
- popular templates vs long-tail queries

Expected lesson:

- LFU protects globally reused items better than LRU

### Week 4 — Semantic-aware

Implement:

- store embedding per item
- compute redundancy score
- evict most redundant item when full

Run scenarios:

- duplicate chunk ingestion
- similar retrieval chunks
- repeated near-identical semantic memories

Expected lesson:

- semantic-aware eviction is useful when capacity should preserve information diversity, not just recency or frequency

## Test Scenarios You Should Simulate

### 1. Cache thrashing under high concurrency

Pattern:

- many unique keys in bursts
- small cache
- low repetition

Measure:

- hit rate collapse
- eviction storm
- hot-item eviction count

Best comparison:

- `LRU` vs `LFU`

### 2. Long-tail prompts crowding out shared prompts

Pattern:

- one globally reused template
- many one-off requests

Measure:

- whether the shared template survives

Best comparison:

- `LFU` should usually beat `LRU`

### 3. Stale data served after TTL too long

Pattern:

- old data reused after the underlying source changed

Measure:

- stale serve count

Best comparison:

- short vs long TTL, not `LRU` vs `LFU`

### 4. Excessive misses due to TTL too short

Pattern:

- same request repeats just after expiry

Measure:

- expiry miss count
- avoidable recomputes

Best comparison:

- `TTL 60s` vs `5m` vs `30m`

### 5. Redundant semantic chunks flooding memory

Pattern:

- many similar retrieval chunks inserted

Measure:

- retained diversity
- downstream relevance quality

Best comparison:

- `LRU` / `LFU` / `FIFO` vs semantic-aware

## How to Benchmark

For each scenario:

- pre-generate a sequence of cache operations
- run the same sequence against each policy
- compare stats side by side

Useful output columns:

- policy
- scenario
- hits
- misses
- hit_rate
- evictions
- expired
- hot_item_survival
- stale_serves

## Real-World Mapping

### Use TTL for

- session memory
- semantic cache
- temporary retrieval results

### Use TTL + LRU for

- chat history window caches
- per-session hot state

### Use TTL + LFU for

- shared templates
- common tool outputs
- reusable base contexts

### Use FIFO mainly for

- baseline comparison
- simple queue-like stores

### Use semantic-aware for

- RAG chunk caches
- vector memory pruning
- duplicate retrieval suppression

## Best Next Step

Start with a single-file eviction benchmark that compares:

- TTL-only
- TTL + LRU
- TTL + LFU

On two scenarios:

- active chat recency
- shared-template popularity

That will teach the most with the least code.

## Lecture 1 — TTL Is a Freshness Control, Not a Capacity Policy

This is the correct starting point.

What this first part teaches:

### 1. TTL is a freshness control

This lab makes that explicit by tracking:

- `stale_serves`
- `expiry_misses`
- `avg_item_age_at_hit`

That is exactly the right starting point.

### 2. `source_version` simulates real-world data change

A cache does not know by magic whether data is stale.

So in the lab, the underlying source changes are simulated with:

```python
source_version
```

If the cache returns version `1` while the source is now version `2`, that counts as:

```python
stale_serves += 1
```

That makes the stale/fresh tradeoff measurable instead of theoretical.

### 3. The Week 1 starter scenarios are the right ones

#### `repeats_just_after_expiry`

Shows:

- TTL too short causes avoidable recompute
- hit rate drops because the repeated request happens just after expiry

#### `source_changes_but_ttl_long`

Shows:

- TTL too long increases stale reuse

#### `stable_vs_unstable_mix`

Shows:

- one TTL is often not ideal for all object types

### Run the TTL lab

```bash
python ttl_lab.py
```

Sample output:

```text
scenario                    | ttl | requests | hits | misses | hit_rate | expired_entries | expiry_misses | stale_serves | writes | avg_item_age_at_hit
----------------------------+-----+----------+------+--------+----------+-----------------+---------------+--------------+--------+--------------------
repeats_just_after_expiry   | 30  | 7        | 2    | 5      | 0.2857   | 4               | 4             | 0            | 5      | 29.0
repeats_just_after_expiry   | 60  | 7        | 3    | 4      | 0.4286   | 3               | 3             | 0            | 4      | 29.33
repeats_just_after_expiry   | 300 | 7        | 6    | 1      | 0.8571   | 0               | 0             | 0            | 1      | 105.5
source_changes_but_ttl_long | 30  | 7        | 3    | 4      | 0.4286   | 3               | 3             | 0            | 4      | 13.33
source_changes_but_ttl_long | 60  | 7        | 4    | 3      | 0.5714   | 2               | 2             | 2            | 3      | 30.0
source_changes_but_ttl_long | 300 | 7        | 6    | 1      | 0.8571   | 0               | 0             | 5            | 1      | 65.0
stable_vs_unstable_mix      | 30  | 12       | 4    | 8      | 0.3333   | 5               | 5             | 1            | 8      | 18.75
stable_vs_unstable_mix      | 60  | 12       | 6    | 6      | 0.5      | 3               | 3             | 2            | 6      | 30.0
stable_vs_unstable_mix      | 300 | 12       | 9    | 3      | 0.75     | 0               | 0             | 4            | 3      | 49.44
```

Lecture takeaway:

- shorter TTL improves freshness but lowers reuse
- longer TTL improves hit rate but risks stale serves
- one global TTL is rarely the best design

## Lecture 2 — TTL + LRU

This is the right Part 2 because `TTL` stays the freshness layer and `LRU` becomes the capacity layer.

That is the design rule:

- check expiry
- remove expired entries first
- only then use `LRU` if capacity is still exceeded

### Why `ttl_resolver(key)` matters

This is the real upgrade beyond the first TTL-only version:

```python
ttl = self.ttl_resolver(key)
```

That lets unstable objects like:

- `stock:*`
- `news:*`

expire faster than:

- `session:*`

This teaches the real lesson: different object classes need different freshness windows.

### What this lab should show

#### `fixed_60s` vs `per_key_ttl`

This is the most useful immediate comparison.

In `stable_vs_unstable_ttl_classes`, you should usually see:

- `fixed_60s` may keep `stock:*` alive too long and increase `stale_serves`
- `per_key_ttl` should reduce stale `stock:*` and `news:*` reuse
- `session:*` should still keep decent reuse because its TTL is longer

That is the main educational win of this step.

#### `active_chat_recency`

This is where `LRU` should behave naturally because:

- recent session keys stay hot
- old session and tool keys are more likely to be evicted
- hot-item survival should be decent unless capacity is too small

#### `shared_template_popularity`

`LRU` will do okay, but not perfectly.

That is useful because it sets up the next lesson:

- `LRU` favors recency
- `LFU` favors global popularity

#### `long_tail_vs_shared_assets`

This is the real `LFU` bridge scenario.

Expected:

- `LFU` should beat `LRU`
- globally useful shared keys should survive longer
- reusable assets like `tool:template:system` and policy or schema keys should stay alive more reliably

### The roadmap after TTL + LRU

The clean learning path is:

- Part 1 — TTL-only
- Part 2 — TTL + LRU
- Part 3 — TTL + LFU
- Part 4 — TTL + FIFO baseline
- Part 5 — semantic-aware redundancy pruning

## Lecture 3 — FIFO as a Baseline

FIFO is not the target winner. It is the baseline policy.

What FIFO means here:

- remove expired entries first
- if still over capacity, evict the oldest inserted entry

FIFO does not care about:

- recent access
- frequency
- semantic redundancy

That is why it is easy to implement and often weak in practice.

### What FIFO should teach you

#### 1. FIFO is simple

That is its main strength.

#### 2. FIFO usually underperforms for LLM workloads

Because it ignores both:

- recency
- frequency

An item can be:

- heavily reused
- still useful
- still likely to be requested again

and FIFO will still evict it just because it was inserted earlier.

#### 3. `fifo_bad_case` should expose that clearly

Expected:

- FIFO evicts early shared assets too aggressively
- `LRU` should protect recently reused ones better
- `LFU` should protect globally popular ones best

### How to interpret FIFO results

Focus on:

- `hit_rate`
- `shared_key_evictions`
- `shared_survival_rate`
- `hot_item_evictions`

If FIFO is bad for a scenario, you will usually see:

- lower `hit_rate`
- higher `shared_key_evictions`
- lower `shared_survival_rate`
- more `hot_item_evictions`

That is the signal that insertion order is not a good proxy for value.

### Practical conclusion

FIFO is acceptable for:

- simple queue-like temporary buffers
- very cheap recompute workloads
- baseline comparison

FIFO is usually not ideal for:

- active conversation state
- shared reusable prompt assets
- hot retrieval caches
- any workload where reuse matters

## Lecture 4 — Semantic-Aware Eviction

This is where the lab becomes truly relevant for:

- RAG chunk stores
- semantic memory
- duplicate retrieval suppression

The question is no longer:

- what was used most recently?
- what was used most often?

The question becomes:

- which retained items are too semantically similar to each other?

### Core idea

Keep the same outer rule:

- remove expired items first
- if still over capacity, apply capacity eviction

But now the capacity eviction becomes:

- evict the most redundant item

Meaning:

- compute how similar each item is to the rest of the cache
- the item with the highest redundancy score is the best eviction target
- this preserves information diversity, not just recency or frequency

### What to add conceptually

Each cache entry now may store:

- `key`
- `created_at`
- `last_access_at`
- `access_count`
- `ttl_seconds`
- `semantic_vector`

Then the semantic policy does:

- compare vectors
- compute pairwise similarity
- score each item by average or max similarity to others
- evict the item with the highest redundancy score

For a first implementation, use:

- cosine similarity
- average similarity to all other items

So:

- high average similarity = more redundant
- low average similarity = more unique

### Important architectural rule

Do not make semantic-aware compete with TTL.

Still do:

- purge expired first
- if over capacity, semantic eviction among remaining items

So semantic-aware remains a capacity policy, not a freshness policy.

### What this should teach

#### 1. `LRU`, `LFU`, and `FIFO` are not diversity-aware

They only look at:

- time
- frequency
- insertion order

So they can retain multiple near-duplicate chunks while discarding a more unique item.

That is bad for retrieval diversity.

#### 2. Semantic-aware eviction should preserve topic coverage

In duplicate-heavy scenarios, it should try to keep something like:

- one representative from cluster A
- one from cluster B
- one from cluster C

instead of many near-identical A chunks.

#### 3. `retained_diversity_score` becomes the key metric

A higher value means:

- retained items are less similar to each other
- memory is more diverse
- the retrieval set likely covers more distinct information

This matters more than pure hit rate in semantic stores.

### Expected result pattern

In `semantic_duplicates`, you should usually see:

- `TTL + Semantic` has the best `retained_diversity_score`
- generic policies may retain too many cluster-A chunks

In `semantic_memory_flood`, you should usually see:

- semantic-aware eviction removes redundant memories
- `LRU`, `LFU`, and `FIFO` may keep too many similar vectors

### Best next improvement

Once this works, the strongest upgrade is a hybrid semantic policy.

Instead of evicting purely by redundancy, score items like:

```python
eviction_score = (
    redundancy_weight * redundancy_score
    - recency_weight * normalized_recency
    - frequency_weight * normalized_frequency
)
```

Meaning:

- high redundancy pushes toward eviction
- recent use protects an item
- frequent use protects an item

That gets much closer to real retrieval-memory systems.

### Practical interpretation

Use semantic-aware eviction when:

- storage is limited
- many items are near-duplicates
- diversity matters more than raw cache hits
- you are building RAG or semantic memory

Use `LRU` or `LFU` when:

- exact reuse matters more than diversity
- cache keys represent exact objects or sessions
- you care more about hot reuse than semantic coverage

## Running the Lab

Install dependencies:

```bash
uv sync
```

Run the TTL lecture lab:

```bash
python ttl_lab.py
```

Run the main eviction benchmark:

```bash
python benchmark_eviction.py
```

Run the semantic eviction benchmark:

```bash
python3 benchmark_eviction_semantic.py
```

## Benchmark Output: Non-Semantic Policies

From the project folder:

```bash
python benchmark_eviction.py
```

Representative output excerpt:

```text
scenario                       | policy   | ttl_mode    | max_entries | requests | hits | misses | hit_rate | evictions | expired_entries | expiry_misses | stale_serves | hot_item_evictions | shared_key_evictions | shared_survivors | shared_survival_rate
-------------------------------+----------+-------------+-------------+----------+------+--------+----------+-----------+-----------------+---------------+--------------+--------------------+----------------------+------------------+---------------------
active_chat_recency            | TTL+LRU  | fixed_60s   | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0
active_chat_recency            | TTL+LFU  | fixed_60s   | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0
active_chat_recency            | TTL+FIFO | fixed_60s   | 4           | 16       | 7    | 9      | 0.4375   | 5         | 0               | 0             | 0            | 1                  | 0                    | 0                | 0.0
shared_template_popularity     | TTL+LRU  | fixed_60s   | 4           | 15       | 6    | 9      | 0.4      | 5         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333
shared_template_popularity     | TTL+LFU  | fixed_60s   | 4           | 15       | 7    | 8      | 0.4667   | 4         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333
shared_template_popularity     | TTL+FIFO | fixed_60s   | 4           | 15       | 5    | 10     | 0.3333   | 6         | 0               | 0             | 0            | 2                  | 1                    | 1                | 0.3333
long_tail_vs_shared_assets     | TTL+LRU  | fixed_60s   | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667
long_tail_vs_shared_assets     | TTL+LFU  | fixed_60s   | 4           | 24       | 8    | 16     | 0.3333   | 12        | 0               | 0             | 0            | 0                  | 3                    | 2                | 0.6667
long_tail_vs_shared_assets     | TTL+FIFO | fixed_60s   | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667
```

Lecture interpretation:

- `LRU` feels natural for active session-like workloads
- `LFU` wins when shared global assets need to survive long-tail pressure
- `FIFO` is useful mostly because it shows you what a weak baseline looks like

## Benchmark Output: Semantic Eviction

Run:

```bash
python3 benchmark_eviction_semantic.py
```

What to focus on:

- `semantic_evictions`
- `avg_evicted_redundancy_score`
- `retained_diversity_score`

Expected result pattern:

- `TTL + Semantic` should preserve diversity better than `LRU`, `LFU`, or `FIFO`
- generic policies may keep too many near-duplicate items

## Final Teaching Summary

If this lab works as intended, the lecture takeaway should be:

1. `TTL` is about freshness, not capacity.
2. `LRU` is good for recent interactive state.
3. `LFU` is good for globally reused shared assets.
4. `FIFO` is a baseline, not usually a production winner.
5. semantic-aware eviction matters when diversity matters more than raw reuse.

That is the whole progression:

- start with freshness
- add capacity pressure
- compare recency vs popularity
- use FIFO to understand what weaker policies miss
- end with redundancy-aware memory pruning for semantic systems





Part 6 = hybrid semantic policy is where the lab becomes much closer to a real retrieval memory controller.

Because pure semantic eviction is good at removing redundancy, but it can still make bad decisions if it ignores:

recent usefulness
repeated usefulness

So now the comparison becomes:

TTL + Semantic-only
TTL + LRU
TTL + LFU
TTL + Hybrid semantic-recency
TTL + Hybrid semantic-frequency
What Part 6 should teach
Semantic-only

Best at redundancy pruning, but may evict an item that is still operationally valuable.

LRU

Good for recent working sets, but blind to semantic duplication.

LFU

Good for globally popular assets, but blind to redundancy.

Hybrid semantic-recency

Best when you want:

diversity
plus protection for recently useful chunks
Hybrid semantic-frequency

Best when you want:

diversity
plus protection for frequently reused chunks
The scoring idea

Instead of evicting by one signal only, compute an eviction score.

Higher score = more likely to evict.

A clean starting formula is:

eviction_score =
    redundancy_weight * redundancy_score
    - recency_weight * normalized_recency
    - frequency_weight * normalized_frequency

Meaning:

high redundancy pushes toward eviction
high recency protects from eviction
high frequency protects from eviction

You do not need both recency and frequency in the same first hybrid step.
Split them into two separate policies first.

Best first design

Build two hybrid selectors:

1. Hybrid semantic-recency
score = redundancy_weight * redundancy - recency_weight * recency
2. Hybrid semantic-frequency
score = redundancy_weight * redundancy - frequency_weight * frequency

That keeps the experiment interpretable.

Recommended normalization

All components should be normalized to 0..1.

Redundancy

Already close to this if cosine similarity averages are used.

Recency

Use relative recency inside the current cache:

normalized_recency = (last_access_at - min_last_access) / (max_last_access - min_last_access)

If all equal, return 0.0.

Frequency

Use relative access count:

normalized_frequency = (access_count - min_access) / (max_access - min_access)

If all equal, return 0.0.