Good. Part 7 should be built as a **controlled eviction lab**, not just theory.

The key idea is:

* **TTL** solves freshness
* **LRU/LFU/FIFO** solve capacity pressure
* **semantic-aware eviction** solves redundancy/diversity in retrieved memory

So do not compare them as if they solve the same problem. In practice, most systems use **TTL plus one capacity policy**.

# The right learning order

## 1. TTL first

Best first because it is easiest to reason about and immediately useful.

Use TTL for:

* session memory
* temporary tool results
* semantic cache entries
* exact answer cache
* retrieval results from unstable sources

What you learn:

* stale vs fresh tradeoff
* short TTL causing misses
* long TTL causing bad or outdated reuse

## 2. TTL + LRU second

Best next step for recent-turn memory and hot working sets.

Use for:

* recent conversation state
* recent retrieval chunks
* exact cache entries for active sessions

What you learn:

* recency bias
* cache thrashing
* hot set stability

## 3. TTL + LFU third

Best for shared reusable assets.

Use for:

* common prompt templates
* org policy blocks
* frequently reused tool schemas
* common FAQ responses

What you learn:

* popularity vs recency
* preserving globally useful entries
* long-tail prompt pressure

## 4. FIFO fourth

Mostly for comparison.

Use for:

* simple queue-like temporary caches
* baseline experiments

What you learn:

* why simple eviction often underperforms for LLM workloads

## 5. Semantic-aware eviction last

Advanced stage.

Use for:

* vector retrieval caches
* semantic memory stores
* RAG chunk stores where diversity matters more than raw count

What you learn:

* redundancy pruning
* diversity preservation
* why “most similar to others” can be the best eviction target

# Best implementation approach

Do this as **one lab with pluggable policies**.

Build a tiny cache simulator or service that supports:

* `put(key, value, metadata)`
* `get(key)`
* `evict_if_needed()`

Each entry should store:

* key
* created_at
* last_access_at
* access_count
* ttl_seconds
* size_estimate
* semantic_vector or redundancy score later

# Suggested project structure

```text
eviction-lab/
├─ cache_policies.py
├─ cache_store.py
├─ benchmark_eviction.py
├─ scenarios.py
├─ analyze_results.py
└─ pyproject.toml
```

# What to build first

## `cache_store.py`

A generic in-memory cache with:

* max entries
* TTL support
* pluggable eviction policy

## `cache_policies.py`

Implement:

* TTL expiry
* LRU
* LFU
* FIFO
* semantic-aware

## `scenarios.py`

Create workloads:

* active conversation sessions
* shared templates
* long-tail prompts
* stale data patterns
* concurrency-like repeated bursts

## `benchmark_eviction.py`

Run scenarios against each policy and record:

* hit rate
* stale hits
* evictions
* average latency proxy
* hot-item survival rate

# Metrics to track

For every policy, record:

* request count
* hit count
* miss count
* eviction count
* expired entry count
* stale serve count
* hot-item eviction count
* average age of evicted entries
* average access count of evicted entries

For semantic-aware later:

* redundancy score of evicted item
* diversity score of retained set

# Metrics that matter most by policy

## TTL

* stale serve count
* expiry miss count
* hit rate
* average item age at hit

## LRU

* hit rate under bursty recency workloads
* eviction count
* hot-item survival

## LFU

* hit rate under repeated shared-template workloads
* long-tail suppression
* popular-item retention

## FIFO

* hit rate baseline
* avoid using it as your target winner

## Semantic-aware

* retrieval diversity
* duplicate reduction
* answer quality downstream

# Practical weekly roadmap

## Week 1 — TTL-only

Implement:

* exact cache entries with TTL
* session entries with TTL
* expiry checks on get/put

Run scenarios:

* TTL too short
* TTL too long
* stable vs unstable data

Expected lesson:

* freshness is not free; aggressive TTL kills hit rate

## Week 2 — TTL + LRU

Implement:

* capacity limit
* evict expired first
* then evict least recently used

Run scenarios:

* active session burst
* recent-turn chat
* hot working set

Expected lesson:

* LRU is strong for active chat/state workloads

## Week 3 — TTL + LFU

Implement:

* expire first
* then evict lowest-frequency items

Run scenarios:

* shared system prompts
* common FAQs
* popular templates vs long-tail queries

Expected lesson:

* LFU protects globally reused items better than LRU

## Week 4 — semantic-aware

Implement:

* store embedding per item
* compute redundancy score
* evict most redundant item when full

Run scenarios:

* duplicate chunk ingestion
* similar retrieval chunks
* repeated near-identical semantic memories

Expected lesson:

* semantic-aware eviction is useful when capacity should preserve information diversity, not just recency/frequency

# Best eviction order inside the cache

When capacity is exceeded, do this:

1. remove expired items first
2. if still over capacity, apply policy:

   * LRU or LFU or FIFO
3. if semantic-aware mode enabled, use redundancy-aware selection among eligible items

That means TTL is the outer freshness filter, not a competing policy.

# Test scenarios you should simulate

## 1. Cache thrashing under high concurrency

Pattern:

* many unique keys in bursts
* small cache
* low repetition

Measure:

* hit rate collapse
* eviction storm
* hot-item eviction count

Best comparison:

* LRU vs LFU

## 2. Long-tail prompts crowding out shared prompts

Pattern:

* one globally reused template
* many one-off requests

Measure:

* whether shared template survives

Best comparison:

* LFU usually should beat LRU

## 3. Stale data served after TTL too long

Pattern:

* old data reused after underlying source changed

Measure:

* stale serve count

Best comparison:

* short vs long TTL, not LRU vs LFU

## 4. Excessive misses due to TTL too short

Pattern:

* same request repeats just after expiry

Measure:

* expiry miss count
* avoidable recomputes

Best comparison:

* TTL 60s vs 5m vs 30m

## 5. Redundant semantic chunks flooding memory

Pattern:

* many similar retrieval chunks inserted

Measure:

* retained diversity
* downstream relevance quality

Best comparison:

* LRU/LFU vs semantic-aware

# Minimal code shape

## `cache_policies.py`

```python
from __future__ import annotations

from typing import Dict, Any, Callable


def is_expired(entry: Dict[str, Any], now_ts: float) -> bool:
    ttl = entry.get("ttl_seconds")
    if ttl is None:
        return False
    return (now_ts - entry["created_at"]) > ttl


def select_lru(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(cache.items(), key=lambda kv: kv[1]["last_access_at"])[0]


def select_lfu(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(cache.items(), key=lambda kv: (kv[1]["access_count"], kv[1]["last_access_at"]))[0]


def select_fifo(cache: Dict[str, Dict[str, Any]]) -> str:
    return min(cache.items(), key=lambda kv: kv[1]["created_at"])[0]
```

## `cache_store.py`

```python
from __future__ import annotations

import time
from typing import Any, Dict, Optional, Callable

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

# How to benchmark

For each scenario:

* pre-generate a sequence of cache operations
* run same sequence against each policy
* compare stats side by side

Output table columns:

* policy
* scenario
* hits
* misses
* hit_rate
* evictions
* expired
* hot_item_survival
* stale_serves

# Real-world mapping

## Use TTL for:

* session memory
* semantic cache
* temporary retrieval results

## Use TTL + LRU for:

* chat history window caches
* per-session hot state

## Use TTL + LFU for:

* shared templates
* common tool outputs
* reusable base contexts

## Use FIFO mainly for:

* baseline comparison
* simple queue-like stores

## Use semantic-aware for:

* RAG chunk caches
* vector memory pruning
* duplicate retrieval suppression

# Best next step

Start with a **single-file eviction benchmark** that compares:

* TTL-only
* TTL+LRU
* TTL+LFU

on two scenarios:

* active chat recency
* shared-template popularity

That will teach the most with the least code.

I can write that benchmark next.


What this first part teaches
1. TTL is a freshness control

This lab makes that explicit by tracking:

stale_serves
expiry_misses
avg_item_age_at_hit

That is the right starting point.

2. source_version simulates real-world data change

This is important.

A cache does not know by magic whether data is stale.
So in the lab we simulate the underlying source changing with:

source_version

If cache returns version 1 while source is now version 2, that counts as:

stale_serves += 1

That gives you a measurable stale/fresh tradeoff.

3. The three starter scenarios are correct for Week 1
repeats_just_after_expiry

Shows:

TTL too short causes avoidable recompute
hit rate drops because repeated request happens just after expiry
source_changes_but_ttl_long

Shows:

TTL too long increases stale reuse
stable_vs_unstable_mix

Shows:

one TTL is often not ideal for all object types

That is a very practical lesson.

python ttl_lab.py


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



Why this version is the right Part 2
1. TTL is still the outer freshness filter

The store does this:

check expiry
remove expired entries first
only then use LRU if capacity is still exceeded

That matches the design rule you described.

2. Per-key TTL classes are now built in

This is the important upgrade from Part 1.

Instead of forcing one global TTL, the store uses:

ttl = self.ttl_resolver(key)

So unstable objects like:

stock:*
news:*

can expire faster than:

session:*

That teaches the real lesson: different object classes need different freshness windows.

3. LRU is isolated as the capacity policy

This is correct architecturally.

TTL is not competing with LRU.
TTL handles freshness.
LRU handles capacity pressure.

That separation will make LFU and FIFO easy to add later.

What this lab will show
fixed_60s vs per_key_ttl

This is the most useful immediate comparison.

In stable_vs_unstable_ttl_classes

you should usually see:

fixed_60s may keep stock:* alive too long → more stale_serves
per_key_ttl should reduce stale stock/news reuse
session:* should still keep decent reuse because its TTL is longer

That is the main educational win of this step.

In active_chat_recency

You should see LRU behaving reasonably well because:

recent session keys stay hot
old session/tool keys are more likely to be evicted
hot-item survival should be decent unless capacity is too small
In shared_template_popularity

LRU will do okay, but not perfectly.

That is useful, because it sets up the next lesson:

LRU favors recency
LFU favors global popularity

So this scenario becomes your bridge into Part 3 = TTL + LFU.


1. active_chat_recency

Usually:

TTL+LRU should do better or at least feel more natural
because recent session state matters more than historical frequency

This is the scenario where recency wins.

2. shared_template_popularity

Usually:

TTL+LFU should start to look better
because reused templates/policies keep surviving

This is the bridge scenario.

3. long_tail_vs_shared_assets

This is the real LFU test.

Expected:

LFU should beat LRU
fewer evictions of globally useful keys
better survival of:
tool:template:system
tool:policy:security
tool:schema:extract

This is the scenario that teaches:

popularity beats recency for shared reusable assets

4. stable_vs_unstable_ttl_classes

Expected:

per-key TTL reduces stale serves for stock:* and news:*
regardless of LRU/LFU, TTL classing still matters

This is good because it reinforces the architecture:

TTL handles freshness
LRU/LFU handle capacity

The next part should be FIFO, but only as a baseline.
After that, move to semantic-aware eviction.

So the roadmap becomes:

Part 1 — TTL-only
Part 2 — TTL + LRU
Part 3 — TTL + LFU
Part 4 — TTL + FIFO baseline
Part 5 — semantic-aware redundancy pruning

This is not the target winner.
It is the baseline policy.

FIFO is useful because it gives you a simple comparison point:

TTL still handles freshness
FIFO handles capacity in the simplest possible way
then you compare FIFO against LRU and LFU to see why it usually loses for LAG/LLM-style workloads
What FIFO means here

When capacity is exceeded:

remove expired entries first
if still over capacity, evict the oldest inserted entry

FIFO does not care about:

recent access
frequency
semantic redundancy

That is why it is easy to implement and often weak in practice.
What FIFO should teach you
1. FIFO is simple

That is its main strength.

It is easy to reason about and easy to implement.

2. FIFO usually underperforms for LLM workloads

Because it ignores both:

recency
frequency

That means an item can be:

heavily reused
still useful
still likely to be requested again

and FIFO will still evict it just because it was inserted earlier.

3. The fifo_bad_case scenario should expose that clearly

Expected:

FIFO evicts early shared assets too aggressively
LRU should protect recently reused ones better
LFU should protect globally popular ones best

So this scenario becomes a very clean teaching example.

How to interpret results

Focus on these columns for FIFO:

hit_rate
shared_key_evictions
shared_survival_rate
hot_item_evictions
If FIFO is bad for a scenario, you will often see:
lower hit_rate
higher shared_key_evictions
lower shared_survival_rate
more hot_item_evictions

That is the signal that insertion order is not a good proxy for value.

Practical conclusion you should reach

After you run FIFO, the message should be:

FIFO is acceptable for:
simple queue-like temporary buffers
very cheap recompute workloads
baseline comparison
FIFO is usually not ideal for:
active conversation state
shared reusable prompt assets
hot retrieval caches
any workload where reuse matters

That is exactly why it belongs in the lab, but not usually in production as the main choice.


Part 5 — semantic-aware eviction

That means:

keep TTL as freshness filter
still allow capacity pressure
but when eligible items are similar, evict the most redundant one

That is where the lab becomes truly relevant for:

RAG chunk stores
semantic memory
duplicate retrieval suppression
How to run


Now move to Part 5 = semantic-aware eviction.

This is the advanced stage.

At this point the question is no longer:

“what was used most recently?”
“what was used most often?”

Instead it becomes:

“which retained items are too semantically similar to each other?”

That matters for:

RAG chunk caches
semantic memory stores
retrieval candidate buffers
duplicate or near-duplicate chunk suppression
Core idea

Keep the same outer rule:

remove expired items first
if still over capacity, apply capacity eviction

But now the capacity eviction is:

evict the most redundant item

Meaning:

compute how similar each item is to the rest of the cache
item with the highest redundancy score is the best eviction target
this preserves diversity of information, not just recency/frequency
What to add conceptually

Each cache entry now may store:

key
created_at
last_access_at
access_count
ttl_seconds
semantic_vector

Then the semantic policy does:

compare vectors
compute pairwise similarity
score each item by average or max similarity to others
evict the item with the highest redundancy score
Policy design choice

For a first implementation, use:

cosine similarity

and

average similarity to all other items

That is simple and good enough for the lab.

So:

high average similarity = more redundant
low average similarity = more unique
Important architectural rule

Do not make semantic-aware compete with TTL.

Still do:

purge expired first
if over capacity, semantic eviction among remaining items

So semantic-aware remains a capacity policy, not a freshness policy.


From the project folder:

python benchmark_eviction.py

```
scenario                       | policy   | ttl_mode    | max_entries | requests | hits | misses | hit_rate | evictions | expired_entries | expiry_misses | stale_serves | hot_item_evictions | shared_key_evictions | shared_survivors | shared_survival_rate | avg_item_age_at_hit | avg_age_of_evicted_entries | avg_access_count_of_evicted_entries
-------------------------------+----------+-------------+-------------+----------+------+--------+----------+-----------+-----------------+---------------+--------------+--------------------+----------------------+------------------+----------------------+---------------------+----------------------------+------------------------------------
active_chat_recency            | TTL+LRU  | fixed_60s   | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0                  | 8.0                 | 6.0                        | 1.33                               
active_chat_recency            | TTL+LFU  | fixed_60s   | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0                  | 8.0                 | 4.0                        | 1.0                                
active_chat_recency            | TTL+FIFO | fixed_60s   | 4           | 16       | 7    | 9      | 0.4375   | 5         | 0               | 0             | 0            | 1                  | 0                    | 0                | 0.0                  | 4.57                | 6.8                        | 1.8                                
active_chat_recency            | TTL+LRU  | per_key_ttl | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0                  | 8.0                 | 6.0                        | 1.33                               
active_chat_recency            | TTL+LFU  | per_key_ttl | 4           | 16       | 9    | 7      | 0.5625   | 3         | 0               | 0             | 0            | 0                  | 0                    | 0                | 0.0                  | 8.0                 | 4.0                        | 1.0                                
active_chat_recency            | TTL+FIFO | per_key_ttl | 4           | 16       | 7    | 9      | 0.4375   | 5         | 0               | 0             | 0            | 1                  | 0                    | 0                | 0.0                  | 4.57                | 6.8                        | 1.8                                
shared_template_popularity     | TTL+LRU  | fixed_60s   | 4           | 15       | 6    | 9      | 0.4      | 5         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333               | 5.0                 | 4.6                        | 1.2                                
shared_template_popularity     | TTL+LFU  | fixed_60s   | 4           | 15       | 7    | 8      | 0.4667   | 4         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333               | 6.57                | 3.75                       | 1.0                                
shared_template_popularity     | TTL+FIFO | fixed_60s   | 4           | 15       | 5    | 10     | 0.3333   | 6         | 0               | 0             | 0            | 2                  | 1                    | 1                | 0.3333               | 4.6                 | 6.33                       | 1.83                               
shared_template_popularity     | TTL+LRU  | per_key_ttl | 4           | 15       | 6    | 9      | 0.4      | 5         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333               | 5.0                 | 4.6                        | 1.2                                
shared_template_popularity     | TTL+LFU  | per_key_ttl | 4           | 15       | 7    | 8      | 0.4667   | 4         | 0               | 0             | 0            | 0                  | 0                    | 1                | 0.3333               | 6.57                | 3.75                       | 1.0                                
shared_template_popularity     | TTL+FIFO | per_key_ttl | 4           | 15       | 5    | 10     | 0.3333   | 6         | 0               | 0             | 0            | 2                  | 1                    | 1                | 0.3333               | 4.6                 | 6.33                       | 1.83                               
long_tail_vs_shared_assets     | TTL+LRU  | fixed_60s   | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667               | 3.0                 | 4.33                       | 1.11                               
long_tail_vs_shared_assets     | TTL+LFU  | fixed_60s   | 4           | 24       | 8    | 16     | 0.3333   | 12        | 0               | 0             | 0            | 0                  | 3                    | 2                | 0.6667               | 12.75               | 2.83                       | 1.0                                
long_tail_vs_shared_assets     | TTL+FIFO | fixed_60s   | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667               | 3.0                 | 4.33                       | 1.11                               
long_tail_vs_shared_assets     | TTL+LRU  | per_key_ttl | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667               | 3.0                 | 4.33                       | 1.11                               
long_tail_vs_shared_assets     | TTL+LFU  | per_key_ttl | 4           | 24       | 8    | 16     | 0.3333   | 12        | 0               | 0             | 0            | 0                  | 3                    | 2                | 0.6667               | 12.75               | 2.83                       | 1.0                                
long_tail_vs_shared_assets     | TTL+FIFO | per_key_ttl | 4           | 24       | 2    | 22     | 0.0833   | 18        | 0               | 0             | 0            | 0                  | 9                    | 2                | 0.6667               | 3.0                 | 4.33                       | 1.11                               
stable_vs_unstable_ttl_classes | TTL+LRU  | fixed_60s   | 4           | 14       | 5    | 9      | 0.3571   | 0         | 7               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 29.4                | 0.0                        | 0.0                                
stable_vs_unstable_ttl_classes | TTL+LFU  | fixed_60s   | 4           | 14       | 5    | 9      | 0.3571   | 0         | 7               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 29.4                | 0.0                        | 0.0                                
stable_vs_unstable_ttl_classes | TTL+FIFO | fixed_60s   | 4           | 14       | 5    | 9      | 0.3571   | 0         | 7               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 29.4                | 0.0                        | 0.0                                
stable_vs_unstable_ttl_classes | TTL+LRU  | per_key_ttl | 4           | 14       | 7    | 7      | 0.5      | 0         | 3               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 68.14               | 0.0                        | 0.0                                
stable_vs_unstable_ttl_classes | TTL+LFU  | per_key_ttl | 4           | 14       | 7    | 7      | 0.5      | 0         | 3               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 68.14               | 0.0                        | 0.0                                
stable_vs_unstable_ttl_classes | TTL+FIFO | per_key_ttl | 4           | 14       | 7    | 7      | 0.5      | 0         | 3               | 2             | 3            | 0                  | 0                    | 0                | 0.0                  | 68.14               | 0.0                        | 0.0                                
fifo_bad_case                  | TTL+LRU  | fixed_60s   | 4           | 15       | 2    | 13     | 0.1333   | 9         | 0               | 0             | 0            | 1                  | 2                    | 2                | 0.6667               | 6.0                 | 4.89                       | 1.22                               
fifo_bad_case                  | TTL+LFU  | fixed_60s   | 4           | 15       | 3    | 12     | 0.2      | 8         | 0               | 0             | 0            | 0                  | 1                    | 2                | 0.6667               | 8.67                | 3.75                       | 1.0                                
fifo_bad_case                  | TTL+FIFO | fixed_60s   | 4           | 15       | 1    | 14     | 0.0667   | 10        | 0               | 0             | 0            | 0                  | 3                    | 2                | 0.6667               | 4.0                 | 4.4                        | 1.1                                
fifo_bad_case                  | TTL+LRU  | per_key_ttl | 4           | 15       | 2    | 13     | 0.1333   | 9         | 0               | 0             | 0            | 1                  | 2                    | 2                | 0.6667               | 6.0                 | 4.89                       | 1.22                               
fifo_bad_case                  | TTL+LFU  | per_key_ttl | 4           | 15       | 3    | 12     | 0.2      | 8         | 0               | 0             | 0            | 0                  | 1                    | 2                | 0.6667               | 8.67                | 3.75                       | 1.0                                
fifo_bad_case                  | TTL+FIFO | per_key_ttl | 4           | 15       | 1    | 14     | 0.0667   | 10        | 0               | 0             | 0            | 0                  | 3                    | 2                | 0.6667               | 4.0                 | 4.4                                 
```