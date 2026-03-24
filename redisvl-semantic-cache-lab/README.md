# RedisVL Semantic Cache Lab

Good choice. RedisVL `SemanticCache` is the right next lab after exact Redis caching because it stays in the same stack, but adds the key ideas of:

- embedding the incoming prompt
- nearest-neighbor search over prior prompts
- threshold-based reuse
- TTL
- tenant scoping / metadata filters

RedisVL’s current docs describe `SemanticCache` exactly this way: embed the prompt, search for a similar cached prompt within a configured `distance_threshold`, and return the cached response if matched. The docs also show TTL support and optional filterable fields for scoped retrieval.

## What You Should Learn in This Lab

### Exact Cache vs Semantic Cache

- Exact cache: same canonical prompt -> same key -> same answer
- Semantic cache: similar prompt meaning -> approximate match -> maybe reuse answer

### Threshold Tuning

RedisVL documents a `distance_threshold` for `SemanticCache`. Lower thresholds are stricter, higher thresholds are looser. In recent RedisVL docs this is described in Redis cosine distance units, where lower values mean more similar and therefore stricter matching.

### False Positives vs False Negatives

- too strict -> miss reusable answers
- too loose -> wrong cached answer

### Multi-Tenant Isolation

RedisVL supports filterable fields in the semantic cache schema, which is the right way to enforce tenant/language/version boundaries instead of sharing one global answer pool.

### Guardrails

Use semantic caching only where answers are stable and low-risk. Redis’s own semantic-cache guidance frames this as a speed/cost optimization for repeated similar requests, not a blind substitute for fresh reasoning in sensitive or rapidly changing domains.

Good fit:

- FAQ
- help center
- stable documentation
- product setup instructions

Bad fit:

- finance
- legal
- real-time status
- personalized user/account state
- rapidly changing information

## What We’ll Build

Lab 3A: FAQ semantic cache

Example pairs:

- "How do I reset my password?"
- "I forgot my password, what should I do?"

Store:

- normalized prompt
- prompt embedding
- answer
- metadata:
  - tenant_id
  - language
  - version
  - category
- TTL

Measure:

- semantic cache hit rate
- average similarity/distance of hits
- wrong-hit rate
- saved LLM calls

## Setup

```bash
uv add fastapi "uvicorn[standard]" httpx pydantic pandas redisvl sentence-transformers
```

This uses a fully local stack:

- Redis
- RedisVL
- local embedding model
- local LLM backend like Ollama

RedisVL’s guides and API docs cover `SemanticCache`, TTL, and vectorizer-backed cache workflows.

## Start Redis

```bash
docker run --name redisvl-semantic-cache -p 6379:6379 -d redis:8
```

## Start the Local LLM Backend

For simplicity, keep Ollama for answer generation:

```bash
ollama pull qwen2.5-coder:7b
```

## Run the App

```bash
uv run uvicorn app:app --port 8001 --reload
```

## FAQ Semantic Cache Test With `curl`

### First Question: miss expected

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my password?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true
  }'
```

Response:

```json
{
   "request_id":"f81e001c-81d6-49d1-962f-597cbd486dbd",
   "answer":"To reset your password, follow these steps:\n\n1. Go to the login page of the service.\n2. Click on \"Forgot Password\" or a similar option.\n3. Enter your email address or username associated with your account.\n4. Follow the instructions provided, which may include entering a verification code sent to your email or phone number.\n5. Set a new password that meets any security requirements.\n\nIf you continue to experience issues, contact customer support for assistance.",
   "semantic_cache":{
      "hit":false,
      "distance":null,
      "metadata_scope":{
         "tenant_id":"tenant-001",
         "language":"en",
         "version":"v1",
         "category":"faq"
      }
   },
   "timings":{
      "prompt_assembly_ms":0.07,
      "cache_lookup_ms":236.94,
      "model_ms":22523.67,
      "cache_write_ms":820.46,
      "total_ms":23581.32
   },
   "prompt_stats":{
      "estimated_prompt_tokens":50,
      "prompt_chars":363
   }
}
```

### Similar Question: hit may occur if threshold is appropriate

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I forgot my password, what should I do?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true
  }'
```

```json
{
   "request_id":"c7174614-3d8e-4376-b3c9-bec69a6da94c",
   "answer":"To reset your password:\n\n1. Go to the login page of the service where you need to reset it.\n2. Click on \"Forgot Password\" or a similar option.\n3. Enter your registered email address or username.\n4. Follow the instructions provided, which may include verifying your identity via email or security questions.\n5. Set a new password that meets any requirements specified by the service.\n\nIf you encounter issues, contact customer support for assistance.",
   "semantic_cache":{
      "hit":false,
      "distance":null,
      "metadata_scope":{
         "tenant_id":"tenant-001",
         "language":"en",
         "version":"v1",
         "category":"faq"
      }
   },
   "timings":{
      "prompt_assembly_ms":0.33,
      "cache_lookup_ms":451.1,
      "model_ms":5378.17,
      "cache_write_ms":306.69,
      "total_ms":6136.51
   },
   "prompt_stats":{
      "estimated_prompt_tokens":52,
      "prompt_chars":375
   }
}
```

## Inspect With `jq`

```bash
curl -s -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I forgot my password, what should I do?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true
  }' | jq '{
    semantic_cache: .semantic_cache,
    timings: .timings,
    prompt_stats: .prompt_stats
  }'
```

Expected:

- first request: semantic miss, model called
- semantically similar second request: possible hit with low distance and `model_ms = 0`

## Multi-Tenant Isolation Test

Tenant isolation is essential. With filterable fields, RedisVL supports scoped retrieval so a hit in tenant A does not bleed into tenant B.

### Store under `tenant-001`

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "How do I reset my password?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true
  }'
```

### Similar question under `tenant-002` should miss

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I forgot my password, what should I do?",
    "tenant_id": "tenant-002",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true
  }'
```

Expected:

- no cross-tenant reuse

## Threshold Tuning Test

RedisVL documents threshold optimization for semantic systems as a distinct tuning step.

Run the same similar prompt with different thresholds.

### Strict threshold

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I forgot my password, what should I do?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true,
    "distance_threshold": 0.08
  }'
```

### Looser threshold

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I forgot my password, what should I do?",
    "tenant_id": "tenant-001",
    "language": "en",
    "version": "v1",
    "category": "faq",
    "use_semantic_cache": true,
    "distance_threshold": 0.25
  }'
```

Observe:

- strict threshold -> fewer hits, fewer wrong hits
- loose threshold -> more hits, more wrong-hit risk

## Benchmark

```bash
uv run python benchmark_semantic_cache.py
uv run python analyze_results.py
```
