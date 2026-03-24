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

6) Run it

Start Ollama and Redis, then:

uv run uvicorn app:app --port 8001 --reload

7) Test flows with curl
A. Start a session

curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "We decided to use Redis for hot session memory and Postgres for durable storage."
  }'


B. Continue same session
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "What database are we using for durable storage?"
  }'

This should benefit from:

recent ordered context
semantic recall
C. Save a tool result
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
D. Force Postgres restore
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "session_id": "sess-002",
    "message": "What did we discuss earlier about durable storage?",
    "force_pg_restore": true
  }'



Debug session
curl -s "http://127.0.0.1:8001/session/sess-002?semantic_query=What%20did%20we%20decide%20about%20durable%20storage%3F" | jq

Force restore through debug endpoint
curl -s "http://127.0.0.1:8000/session/sess-002?force_pg_restore=true&semantic_query=What%20database%20did%20we%20choose%3F" | jq
That exercises the cold-start fallback path.

8) What this lab teaches
Session store vs semantic cache vs prompt cache
session store: recent ordered state
semantic recall: relevant old memory by meaning
prompt cache: repeated prefix reuse at inference/provider layer
Short-term vs long-term memory
short-term: recent turns + current summary + latest tool result
long-term: persisted Postgres history + semantic searchable memory
Windowed vs summarized memory
windowed = get_recent(...)
summarized = summary
relevance-based = get_relevant(...)

RedisVL’s current message-history guide explicitly distinguishes recent message retrieval and semantic message retrieval, which maps directly to this design.

9) Best next experiments

Run these:

Experiment 1 — recent continuity

Ask 3–4 linked questions in the same session and inspect:

memory.recent_count
prompt_preview
Experiment 2 — semantic recall

Mention a fact early in the session, then ask about it later with different wording.

Experiment 3 — tool-result reuse

Store a tool result, then ask a follow-up that should use it.

Experiment 4 — Postgres fallback

Force restore and confirm the session still rebuilds.

