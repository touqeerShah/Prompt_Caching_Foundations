This lab is for:

app-layer exact caching
canonical prompt hashing
skipping model calls on exact repeat
logging cache hit/miss behavior
preparing for semantic cache later

This is different from:

vLLM prefix/KV cache: reuse inside inference
llama.cpp session cache: reuse local model state
Redis exact cache: skip the model call entirely if the prompt is identical
Stack
uv for project setup and dependency management. uv init, uv add, and uv run are the current standard project flow.
Redis for exact cache
FastAPI for a tiny API
Ollama as the simple local model backend for this step
later: semantic cache with GPTCache or RedisVL

- Start Redis
If you already have Redis, use that. Otherwise the quickest local setup is Docker:
docker run --name redis-cache-lab -p 6379:6379 -d redis:8

used later GPTCache/RedisVL

uv run uvicorn app:app --port 8001 --reload

curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prefixes help caching.",
    "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
    "use_cache": true
  }'

curl -s -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why stable prefixes help caching.",
    "context": "Prompt caching works best when repeated prefixes remain identical across calls.",
    "use_cache": true
  }' | jq '{
    cache: .cache,
    timings: .timings,
    prompt_stats: .prompt_stats
  }'

uv run python benchmark_exact_cache.py
uv run python analyze_results.py