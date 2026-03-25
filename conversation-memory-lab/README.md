# Conversation Memory Lab

For Part 4, you should treat memory as two layers at once:

## Hot Session State in Redis

This is the sequential conversation state you need to resume a chat quickly:

- session id
- ordered message list
- last tool outputs
- running summary
- TTL

## Semantic Recall With RedisVL

This is for searching past messages, summaries, and tool results by meaning instead of only by recency. RedisVL’s message-history docs explicitly support session-tagged message history, and `SemanticMessageHistory` is intended for relevance-based context retrieval rather than simple chronological replay.

That means your idea is good, but the separation matters:

- session store answers: "What happened in this conversation recently?"
- semantic search over memory/results answers: "What earlier thing is relevant to this new question?"
- semantic answer cache answers: "Can I reuse an old answer instead of calling the model?"

Those are three different jobs.

## Recommended Memory Design

### A. Short-Term Session Memory

Store in Redis:

- `session:{id}:messages`
- `session:{id}:summary`
- `session:{id}:last_tool_results`
- `session:{id}:meta`

Use TTL for inactivity expiry. Redis and RedisVL both document message-history/session patterns for conversational state, and Redis’s current agent-memory docs distinguish short-term session context from longer-term memory.

### B. Semantic Memory Index

Also store selected items into RedisVL for vector retrieval:

- user messages
- assistant messages
- tool outputs
- rolling summaries
- extracted "facts" or decisions

Attach metadata:

- `session_id`
- `user_id`
- `tenant_id`
- `message_type`
- `timestamp`
- `source` (`chat`, `tool`, `summary`, `fact`)
- `version`

RedisVL supports vector search with metadata filters and hybrid retrieval, which is exactly what you want for scoped memory recall.

## The Clean Architecture

### Hot Path

When a new message arrives:

- load recent session messages from Redis
- load compact summary from Redis
- optionally run RedisVL semantic search over:
  - prior messages
  - prior summaries
  - prior tool results
- rebuild prompt from:
  - system prompt
  - summary
  - recent window
  - semantically relevant recalls
  - new user message

### Write Path

After each turn:

- append new messages to Redis history
- update running summary
- store tool result payload if any
- upsert selected artifacts into RedisVL semantic index
- optionally persist durable copy to Postgres

That gives you:

- fast resume
- relevant recall
- cross-server continuity
- durable fallback

## What RedisVL Should Be Used for Here

RedisVL is best for:

### 1. Semantic Message Recall

Example:
User now asks:

"What did we decide earlier about password reset?"

Search past messages/summaries semantically and retrieve only relevant prior turns.

RedisVL’s message-history docs explicitly mention `SemanticMessageHistory` for relevance-based retrieval.

### 2. Semantic Search Over Tool Results

Example:
A prior tool call returned a long policy blob or DB result.
Later the user asks:

"What was the policy about timeout retries?"

Instead of replaying all tool output, vector-search the stored tool result chunks.

### 3. Long-Term Memory / Facts

Example:

- preferred language
- prior decisions
- stable user preferences
- project conventions

These are not just message history; they are extracted memory objects that can be searched by meaning.

## What Should Not Be Done

Do not rely only on semantic search for the active conversation.

You still need:

- the recent ordered window
- the running summary
- exact session state

Semantic retrieval is a supplement, not a replacement, because order and recency matter in live conversations.

## Best Data Split

### Redis Session State

Use plain Redis structures or RedisVL message-history helpers for:

- exact chronological messages
- summary
- current working state
- last tool result pointers
- TTL-based expiry

RedisVL’s current message-history docs store messages with roles like `system`, `user`, and `llm`, and support session tags for multiple conversations/users.

### RedisVL Semantic Index

Use this for:

- recalled memories
- searchable summaries
- searchable tool outputs
- extracted facts/decisions

### Postgres Durable Store

Use this for:

- long-term persistence
- audit trail
- recovery when Redis expires or is flushed
- background analytics

## Lab 4A Design

### Store

For each session:

- `session_id`
- `message_list`
- `last_tool_results`
- `running_summary`
- `ttl`
- semantic memory entries linked by `session_id` and `tenant_id`

### Practice Features

You listed the right ones. Add one more:

- semantic recall of relevant past items

So the exercise becomes:

- resume session from another server
- expire inactive session via TTL
- rebuild prompt from Redis memory
- fallback to Postgres if Redis misses
- retrieve relevant older messages/tool results semantically

## Concrete Memory Policy

### Short-Term

Keep:

- last 10–20 turns exactly
- running summary
- last N tool outputs

### Long-Term

Store semantically:

- decisions
- extracted facts
- stable user preferences
- important tool findings
- major summaries every few turns

Redis’s current memory guidance separates short-term conversation/session state from long-term learned patterns/preferences, which maps directly to this design.

## Suggested Retrieval Policy Per Turn

For each new user message:

- fetch recent window from Redis
- fetch running summary
- run semantic search over same-session memory
- optionally run semantic search over same-user or same-tenant long-term memory
- merge top relevant items into prompt

Use metadata filters such as:

- `tenant_id`
- `user_id`
- `session_id`
- `source`
- `language`

RedisVL supports metadata filtering with vector queries, which is exactly what makes this safe enough for multi-tenant memory recall.

## Best Guardrails

Use semantic recall for:

- stable prior decisions
- past explanations
- tool outputs
- support/chat knowledge
- long-term memory artifacts

Avoid unvalidated semantic recall for:

- highly sensitive personal state
- financial/legal/medical advice
- real-time facts
- auth/account-specific actions without fresh verification

## Recommended Build Order for Part 4

### Step 1

Plain Redis session store:

- messages
- summary
- tool results
- TTL

### Step 2

RedisVL `MessageHistory` / `SemanticMessageHistory` style layer:

- session tags
- semantic recall from prior messages

### Step 3

Index tool results and summaries too:

- searchable memory artifacts

### Step 4

Postgres fallback:

- rebuild session if Redis is cold

## Best Practical Implementation Shape

Use this model:

### Hot state in Redis

- fast read/write
- TTL
- current session continuity

### Durable copy in Postgres

- restore on miss
- long-term audit/history

### RedisVL semantic memory

- relevance-based recall
- summaries + tool outputs + extracted facts

That is the most production-sensible version of "conversation memory cache."

## Setup

```bash
uv add fastapi "uvicorn[standard]" httpx pydantic redis redisvl asyncpg
uv add sentence-transformers
docker run --name redis-memory-lab -p 6379:6379 -d redis:8

docker run --name pg-memory-lab \
  -e POSTGRES_PASSWORD=postgres \
  -e POSTGRES_USER=postgres \
  -e POSTGRES_DB=memorylab \
  -p 5432:5432 -d postgres:16
```

## Run the App

Start Ollama and Redis, then:

```bash
uv run uvicorn app:app --port 8001 --reload
```

## Test Flows With `curl`

### A. Start a session

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "We decided to use Redis for hot session memory and Postgres for durable storage."
  }'
```

### B. Continue the same session

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "What database are we using for durable storage?"
  }'
```

This should benefit from:

- recent ordered context
- semantic recall

### C. Save a tool result

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "Store the last query result for me.",
    "tool_result": {
      "tool": "db_lookup",
      "result": {
        "db": "postgres",
        "purpose": "durable storage"
      }
    }
  }'
```

### D. Force Postgres restore

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "What did we discuss earlier about durable storage?",
    "force_pg_restore": true
  }'
```

### Debug session

```bash
curl -s "http://127.0.0.1:8001/session/sess-002?semantic_query=What%20did%20we%20decide%20about%20durable%20storage%3F" | jq
```

### Force restore through debug endpoint

```bash
curl -s "http://127.0.0.1:8000/session/sess-002?force_pg_restore=true&semantic_query=What%20database%20did%20we%20choose%3F" | jq
```

That exercises the cold-start fallback path.

## What This Lab Teaches

### Session store vs semantic cache vs prompt cache

- session store: recent ordered state
- semantic recall: relevant old memory by meaning
- prompt cache: repeated prefix reuse at inference/provider layer

### Short-term vs long-term memory

- short-term: recent turns + current summary + latest tool result
- long-term: persisted Postgres history + semantic searchable memory

### Windowed vs summarized memory

- windowed = `get_recent(...)`
- summarized = `summary`
- relevance-based = `get_relevant(...)`

RedisVL’s current message-history guide explicitly distinguishes recent message retrieval and semantic message retrieval, which maps directly to this design.

## Best Next Experiments

Run these:

### Experiment 1 — recent continuity

Ask 3–4 linked questions in the same session and inspect:

- `memory.recent_count`
- `prompt_preview`

### Experiment 2 — semantic recall

Mention a fact early in the session, then ask about it later with different wording.

### Experiment 3 — tool-result reuse

Store a tool result, then ask a follow-up that should use it.

### Experiment 4 — Postgres fallback

Force restore and confirm the session still rebuilds.

## Part 5 — Cache Miss Recovery Patterns

This is the operational part you described, and it is very important.

## Recovery Strategy Roadmap

### A. Read-through / lazy loading

If cache miss happens:

- fetch from DB / vector store / object store
- optionally regenerate
- then populate cache
- serve response

This is the easiest pattern and best starting point.

#### Practice

Build a flow:

1. check Redis
2. if miss, read Postgres/vector DB
3. if still missing, recompute with LLM
4. store result in Redis
5. return response

#### Test cases

- cache key absent
- Redis restart
- stale cached object
- source available
- source unavailable

### B. Cache warming

Best for:

- system prompts
- common templates
- organization policy blocks
- top documents
- common user-specific context

Anthropic notes cache hits improve when requests share more cached content and when traffic remains steady enough to avoid expiry. ([Claude API Docs][5])

#### Practice

At app startup:

- precompute embeddings for common prompts
- preload top tenant documents
- send warm-up calls for repeated prefix-heavy workflows
- prefill Redis with common answer templates

#### Test

Compare:

- cold start TTFT
- warm start TTFT
- first-request failure rate
- first-request cost

### C. Graceful degradation

If your preferred source fails:

- use global base context
- use shorter context
- skip expensive retrieval stage
- serve "partial-confidence" answer
- switch model tiers if needed

#### Practice

Create 3 modes:

**Fast mode**

- read from Redis/session memory
- no expensive retrieval
- good for chat continuity

**Fallback mode**

- recompute from vector DB / source DB
- slower but more accurate

**Degraded mode**

- use base system context only
- tell app/UI confidence is lower

#### Test

Kill one dependency at a time:

- Redis down
- vector DB down
- primary DB slow
- embedding service timeout

#### What to record

- fallback activation count
- degraded answer count
- source timeout count
- recovery success rate

### D. Retry mechanisms

Good for transient failures between:

- app ↔ Redis
- app ↔ vector DB
- app ↔ embeddings provider
- app ↔ LLM API

#### Practice

Implement:

- exponential backoff
- jitter
- max retries
- circuit breaker
- timeout budget

#### Test

Simulate:

- 1-second latency spike
- 500 errors
- dropped connection
- partial response timeout

## How to Test Each Recovery Pattern

### A. Read-through / lazy loading

Normal path:

- Redis miss
- Postgres restore
- repopulate Redis
- next request should become fast

Test:

- delete Redis keys for one session
- call `/chat`
- confirm `mode = fallback`
- call again
- confirm `mode = fast`

### B. Cache warming

At startup:

- preload warm summaries and tool context
- compare first request to cold start

Record:

- first request `total_ms`
- first request `recovery_ms`
- first request `model_ms`

### C. Graceful degradation

Simulate dependency failure:

- stop Redis
- or break semantic recall
- or make Postgres unavailable

Expected:

- `mode = degraded`
- `degraded_reason` populated
- answer still returned using base context only

### D. Retry mechanisms

Simulate:

- Redis timeout
- Postgres temporary failure
- Ollama slow response

The retry and backoff should smooth transient failures instead of failing immediately. Tenacity recommends exponential backoff with jitter to reduce collision and herd effects, and `redis-py` supports retry helpers with backoff too.

## What to Record

For each request, add counters or logs for:

- `mode`
- `fallback_activated`
- `degraded_reason`
- `redis_hot_ms`
- `pg_restore_ms`
- `semantic_ms`
- `model_ms`
- `summary_update_ms`
- `recovery_success`

And aggregate:

- fallback activation count
- degraded answer count
- source timeout count
- retry count
- recovery success rate

## Recommended First Run

Use this order:

- run normal chat twice
- clear Redis session state
- run again and observe fallback
- run again and observe fast mode restored
- stop Redis and confirm degraded mode
- restart Redis and confirm recovery returns to fast/fallback path

If you want, next I’ll write the exact patches against your current `app.py` and `memory_store.py` rather than the architectural version.

## Monitoring Model

Use these 6 buckets.

### 1. Provider-native cache metrics

Track when you use OpenAI / Anthropic:

- `provider_cache_hit_rate`
- `provider_cached_tokens`
- `provider_prompt_tokens`
- `provider_cached_token_ratio`
- `provider_ttft_ms`
- `provider_cost_estimate`
- `provider_cache_miss_reason`

OpenAI gives you cached token counts via `prompt_tokens_details.cached_tokens`. Anthropic’s cache TTL behavior means expired is a first-class miss reason.

### 2. Exact Redis cache metrics

Track:

- hit count
- miss count
- lookup latency
- write latency
- miss-to-fill latency
- stale-return count
- eviction-related misses if you can infer them

Redis docs explicitly call out hit ratio and eviction as important observability points.

### 3. Semantic cache metrics

Track:

- semantic hit count
- semantic miss count
- returned similarity/distance
- threshold used
- wrong-hit count
- manual-correction count
- avoided LLM call count

RedisVL semantic caching is threshold-based, so score distribution and threshold choice are load-bearing metrics.

### 4. Memory/session metrics

Track:

- session resume success count
- Postgres restore count
- restore latency
- summary refresh count
- summary skip count
- summary refresh reason
- semantic recall count
- degraded-mode count

### 5. Retrieval fallback metrics

Track:

- vector recall attempted
- vector miss count
- source DB lookup latency
- recompute count
- degraded answer count
- fallback success rate

### 6. Infrastructure metrics

Track:

- Redis availability errors
- Postgres availability errors
- LLM API/model errors
- retry count
- circuit-open count
- timeout count

## Dashboard Design

Build these 6 panels first.

### 1. Hit rate over time

Formula:

- exact Redis hit rate
- semantic hit rate
- provider cache hit rate
- session resume success rate

### 2. TTFT / latency by route

Show:

- `/chat` total
- model time
- recovery time
- summary update time
- Redis lookup time

OpenAI and Anthropic caching both matter mainly because they reduce input-processing latency, especially TTFT and prefill cost.

### 3. Cost by route

For provider-based calls:

- prompt tokens
- cached tokens
- estimated cost per request

Anthropic pricing explicitly distinguishes cache write and cache read pricing, and OpenAI exposes cached-token accounting that you can use for estimates.

### 4. Miss reason breakdown

Bar chart by:

- expired
- key mismatch
- source unavailable
- threshold too strict
- serialization mismatch
- not found

### 5. Recovery mode breakdown

Pie or bar:

- fast
- fallback
- degraded

### 6. Semantic score distribution

Histogram:

- hit distances
- miss distances
- threshold line

This is the most practical way to tune false positives vs false negatives.

## Sample `/metrics` Output

```text
% curl -sL "http://127.0.0.1:8001/metrics"
# HELP python_gc_objects_collected_total Objects collected during gc
# TYPE python_gc_objects_collected_total counter
python_gc_objects_collected_total{generation="0"} 9344.0
python_gc_objects_collected_total{generation="1"} 1390.0
python_gc_objects_collected_total{generation="2"} 117.0
# HELP python_gc_objects_uncollectable_total Uncollectable objects found during GC
# TYPE python_gc_objects_uncollectable_total counter
python_gc_objects_uncollectable_total{generation="0"} 0.0
python_gc_objects_uncollectable_total{generation="1"} 0.0
python_gc_objects_uncollectable_total{generation="2"} 0.0
# HELP python_gc_collections_total Number of times this generation was collected
# TYPE python_gc_collections_total counter
python_gc_collections_total{generation="0"} 883.0
python_gc_collections_total{generation="1"} 80.0
python_gc_collections_total{generation="2"} 6.0
# HELP python_info Python platform information
# TYPE python_info gauge
python_info{implementation="CPython",major="3",minor="12",patchlevel="13",version="3.12.13"} 1.0
# HELP cache_requests_total Total cache requests by cache type, route, and result
# TYPE cache_requests_total counter
# HELP request_mode_total Total requests by route and recovery mode
# TYPE request_mode_total counter
# HELP summary_refresh_total Summary refresh/skip events
# TYPE summary_refresh_total counter
# HELP app_latency_ms Latency in milliseconds for application stages
# TYPE app_latency_ms histogram
# HELP semantic_distance Semantic distance distribution for semantic cache/memory matches
# TYPE semantic_distance histogram
# HELP provider_tokens_total Provider prompt and cached token accounting
# TYPE provider_tokens_total counter
# HELP manual_cache_review_total Manual review outcomes for cache results
# TYPE manual_cache_review_total counter
(conversation-memory-lab) touqeershah@node01s-MacBook-Pro conversation-memory-lab %
```

## Good Test Flow

Do this in order:

### A. Hit your `/chat` endpoint a few times

For example:

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "message": "We decided to use Redis for hot state and Postgres for fallback."
  }'
```

Then:

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-001",
    "message": "What did we decide about storage?"
  }'
```

## Prometheus Setup

```bash
uv add prometheus-client

docker run --name prompt-cache-prometheus \
  -p 9090:9090 \
  -v "$PWD/prometheus.yml:/etc/prometheus/prometheus.yml" \
  prom/prometheus
```

Then open:

```text
http://localhost:9090
```

Test queries in Prometheus UI.

Try these:

- `cache_requests_total`
- `request_mode_total`
- `summary_refresh_total`
- `app_latency_ms_count`
- `app_latency_ms_sum`

## Useful PromQL Examples

### Total chat requests by mode

```promql
sum by (mode) (request_mode_total{route="/chat"})
```

### Cache hits by cache type

```promql
sum by (cache_type, result) (cache_requests_total{route="/chat"})
```

### Semantic misses only

```promql
sum by (reason) (cache_requests_total{cache_type="semantic_memory", result="miss", route="/chat"})
```

### Average model latency

```promql
rate(app_latency_ms_sum{metric="model_ms",route="/chat"}[5m])
/
rate(app_latency_ms_count{metric="model_ms",route="/chat"}[5m])
```

### Average total latency by mode

```promql
rate(app_latency_ms_sum{metric="total_ms",route="/chat"}[5m])
/
rate(app_latency_ms_count{metric="total_ms",route="/chat"}[5m])
```

## Important Note

Because your FastAPI app mounts Prometheus at:

```python
app.mount("/metrics", metrics_app)
```

The correct scrape path is:

```text
metrics_path: /metrics/
```

with the trailing slash.

docker restart prompt-cache-prometheus
