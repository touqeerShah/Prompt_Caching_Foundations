# Prompt Caching Foundations

This repository is a learn-by-building roadmap for understanding prompt caching, application caching, semantic caching, conversation memory, and recovery patterns for LLM systems.

The main idea of the project is simple:

- start with local foundations first
- learn how prompt structure affects reuse
- separate provider-native prompt caching from app-level caching
- measure everything with latency and cache metrics
- add memory, fallback, and observability as the system grows

`Outline.md` is the planning reference for the full roadmap. The folders in this repository are the project labs built from that outline.

## The Big Picture

This project is organized around three major caching layers:

### 1. Provider-native prompt caching

This is caching done by the model provider for repeated input prefixes.

Examples:

- OpenAI prompt caching
- Anthropic prompt caching

This helps when the repeated prefix is stable enough to match the provider’s caching rules.

### 2. Application-level caching

This is your own cache layer in Redis, a database, or a vector store.

Examples:

- exact answer cache
- semantic answer cache
- cached retrieval results
- cached conversation state

This can skip model calls entirely or reduce how much work needs to be done before the model is called.

### 3. Observability and recovery

Caching only becomes useful in practice when you can measure it and recover cleanly from misses or failures.

Examples:

- cache hit rate
- TTFT
- fallback frequency
- stale data behavior
- retry and degradation paths

## Master Roadmap

The repository follows this learning sequence from `Outline.md`.

### Part 0: Foundations first

Learn the basics before any advanced caching work:

- tokenization basics
- context window basics
- static prefix vs dynamic suffix
- request lifecycle
- latency metrics such as retrieval time, TTFT, and total response time

Goal:
build a tiny local chat app that makes prompt assembly and latency visible.

### Part 1: Prefix and prompt design for token reuse

This is where prompt reuse starts.

Core lesson:
put stable shared instructions first and dynamic request-specific content later.

What to learn:

- prompt segmentation
- canonicalization
- deterministic ordering
- prefix stability across requests

Goal:
compare bad, better, and best prompt structures and measure how stable prefixes affect reuse and latency.

### Part 2: Provider-native prompt caching

This part needs a real provider API.

What to learn:

- what counts as a cacheable prefix
- how cache lifetime affects hit rate
- why almost-identical prompts often miss cache
- how cached tokens affect latency and cost

Goal:
run repeated requests against providers like OpenAI or Anthropic and measure cached tokens, TTFT, and cost changes.

### Part 3: Semantic answer caching

This is different from prefix caching.

Instead of reusing repeated input tokens, semantic caching reuses prior answers for similar questions.

What to learn:

- exact cache vs semantic cache
- similarity threshold tuning
- false positives vs false negatives
- multi-tenant isolation

Goal:
reuse safe answers for semantically similar questions without blindly reusing the wrong response.

### Part 4: Conversation memory cache

This is session-state caching rather than prompt caching.

What to learn:

- Redis session memory
- semantic recall over prior messages and tool outputs
- short-term vs long-term memory
- resumability across servers

Goal:
resume conversations, rebuild prompts from stored memory, and combine exact session state with semantic recall.

### Part 5: Cache miss recovery patterns

This is the operational side of the system.

What to learn:

- read-through caching
- cache warming
- graceful degradation
- retry and fallback design

Goal:
make the system reliable when Redis, vector search, embeddings, or the LLM backend fail or miss.

### Part 6: Monitoring and observability

What to learn:

- hit rate tracking
- latency breakdowns
- miss reason analysis
- cost tracking
- semantic-cache quality tracking

Goal:
make cache behavior explainable over time instead of guessing from anecdotal results.

### Part 7: Eviction strategies

What to learn:

- TTL
- LRU
- LFU
- FIFO
- semantic-aware eviction

Goal:
understand how freshness, reuse frequency, and working-set pressure change cache effectiveness.

### Part 8: Efficient retrieval as context optimization

What to learn:

- chunking
- reranking
- top-k tuning
- compression
- hierarchical context aggregation

Goal:
reduce prompt size and latency by retrieving less but better context.

## Repository Structure

Each folder is a separate project with its own `README.md`.

- [llm-foundations/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/llm-foundations/README.md)
  Part 0 foundations: prompt assembly, retrieval stub, token counting, latency, TTFT
- [prefix-prompt/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/prefix-prompt/README.md)
  Part 1 prompt design and canonicalization experiments
- [vllm-prefix-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/vllm-prefix-cache-lab/README.md)
  local prefix/KV caching with vLLM
- [llama-cpp-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/llama-cpp-cache-lab/README.md)
  local single-machine prompt/session cache experiments with `llama-cpp-python`
- [redis-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/redis-cache-lab/README.md)
  exact app-layer caching with Redis
- [redisvl-semantic-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/redisvl-semantic-cache-lab/README.md)
  semantic answer caching with RedisVL
- [conversation-memory-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/conversation-memory-lab/README.md)
  session memory, Redis state, semantic recall, and Postgres fallback

## What Can Be Practiced Locally

These parts can be done fully or mostly locally:

- app-side Redis cache
- exact answer cache
- semantic cache
- conversation/session memory
- retry and fallback logic
- cache warming logic
- prompt canonicalization
- latency measurement
- retrieval optimization
- eviction experiments
- dashboards and metrics

Useful local tools across the repo:

- FastAPI
- Redis
- RedisVL
- Ollama
- vLLM
- `llama-cpp-python`
- Postgres

## What Usually Needs Paid APIs

These parts usually need a real provider:

- provider-native prompt caching
- provider-side cached token accounting
- real billing comparisons
- provider cache lifetime behavior

Best hybrid setup:

- local models for architecture and systems experiments
- one paid provider for true prompt-caching behavior

## How To Use This Repository

1. Start with [llm-foundations/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/llm-foundations/README.md).
2. Move to [prefix-prompt/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/prefix-prompt/README.md) to make prompt structure measurable.
3. Compare local reuse layers in [vllm-prefix-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/vllm-prefix-cache-lab/README.md) and [llama-cpp-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/llama-cpp-cache-lab/README.md).
4. Add app-level caching with [redis-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/redis-cache-lab/README.md) and [redisvl-semantic-cache-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/redisvl-semantic-cache-lab/README.md).
5. Add session memory with [conversation-memory-lab/README.md](/Users/touqeershah/Documents/PharmaTraceProject-Files/Prompt_Caching_Foundations/conversation-memory-lab/README.md).
6. Use `Outline.md` to continue the later roadmap around recovery, monitoring, eviction, and retrieval optimization.

## Core Distinction To Keep Clear

These layers solve different problems:

- provider-native prompt caching:
  can repeated input tokens be reused by the provider?
- inference-side prefix/KV caching:
  can repeated prefix computation be reused inside the model server?
- exact app cache:
  can we skip the model call for the exact same prompt?
- semantic cache:
  can we safely reuse a prior answer for a similar question?
- conversation memory:
  can we reconstruct the session state and relevant history efficiently?

Keeping those separated is the main architectural lesson of the project.
