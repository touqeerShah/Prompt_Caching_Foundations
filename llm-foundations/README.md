# LLM Foundations

Small local demos for learning how prompt structure, retrieval, token counting, and latency measurement work before adding prompt caching.

This folder contains two FastAPI apps:

- `basic-example.py`: non-streaming baseline with simple timing breakdowns
- `basic-example-ttft.py`: streaming version that measures TTFT and uses a real tokenizer when available

Everything is designed to run against a local Ollama server using `qwen2.5-coder:7b`.

## What This Project Covers

- A fixed system prompt as the stable prompt prefix
- Optional retrieval from a tiny in-memory knowledge base
- Prompt assembly into `[SYSTEM]`, `[CONTEXT]`, `[USER]`, and `[ASSISTANT]` sections
- Timing breakdowns for retrieval, prompt assembly, model work, and total request time
- TTFT measurement in the streaming version
- Token counting with either a real Hugging Face tokenizer or a whitespace fallback

## Files

- `basic-example.py`
  - Exposes `POST /chat` and `GET /health`
  - Calls Ollama with `stream=False`
  - Returns `estimated_*` token counts using whitespace splitting
  - Measures `retrieval_ms`, `prompt_assembly_ms`, `model_ms`, and `total_ms`
- `basic-example-ttft.py`
  - Exposes `POST /chat` and `GET /health`
  - Calls Ollama with `stream=True`
  - Measures first-token latency with `ttft_ms`
  - Returns `total_tokens`, `system_tokens`, `context_tokens`, and `user_tokens`
  - Uses `token_utils.best_token_count()` and falls back to whitespace estimation if the tokenizer is unavailable
- `token_utils.py`
  - Loads `Qwen/Qwen2.5-7B-Instruct` with `transformers`
  - Caches the tokenizer with `lru_cache`
- `benchmark.py`
  - Sends a fixed set of requests to `http://127.0.0.1:8001/chat`
  - Writes results to `benchmark_results.csv`
- `analyze_benchmark.py`
  - Reads `benchmark_results.csv` with pandas
  - Prints all rows, averages by retrieval flag, and repeated-prompt comparisons

## Requirements

- Python `3.11`
- A local Ollama server running on `http://localhost:11434`
- The Ollama model `qwen2.5-coder:7b`
- For real token counts in the TTFT app, access to the Hugging Face tokenizer files for `Qwen/Qwen2.5-7B-Instruct` on first use

Install the model if needed:

```bash
ollama pull qwen2.5-coder:7b
```

## Setup

Run everything from inside this directory:

```bash
cd /Prompt_Caching_Foundations/llm-foundations
```

Install dependencies with `uv`:

```bash
uv sync
```

If you prefer a manual virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

## Important Run Note

The demo files use hyphens in their filenames. That means the usual `uvicorn module_name:app` import form does not work cleanly with the files as they currently exist.

The reliable option is to launch them with a small Python loader from inside `llm-foundations`.

That is why the README does not use:

```bash
uvicorn basic-example-ttft:app --port 8001 --reload
```

or:

```bash
uvicorn basic-example:app --port 8001 --reload
```

Those commands match the teaching flow you originally wrote down, but with the current hyphenated filenames they are not standard Python import targets. If you want, we can add tiny wrapper modules or rename the files to underscore-based names so the shorter `uvicorn ...:app` commands work directly.

## Run The Basic App

This version is the simplest baseline. It shows:

- static prefix vs dynamic suffix
- optional retrieval
- prompt assembly
- rough token estimates
- end-to-end timing without TTFT

Start the API on port `8001`:

```bash
./.venv/bin/python -c "
import importlib.util, pathlib, uvicorn
path = pathlib.Path('basic-example.py')
spec = importlib.util.spec_from_file_location('basic_example', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
uvicorn.run(mod.app, host='127.0.0.1', port=8001)
"
```

Health check:

```bash
curl http://127.0.0.1:8001/health
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain why prompt structure matters for caching",
    "use_retrieval": true
  }'
```

Response shape:

```json
{
  "request_id": "...",
  "model": "qwen2.5-coder:7b",
  "answer": "...",
  "prompt_preview": "...",
  "prompt_stats": {
    "estimated_total_tokens": 65,
    "estimated_system_tokens": 24,
    "estimated_context_tokens": 26,
    "estimated_user_tokens": 7,
    "has_retrieval_context": true
  },
  "timings": {
    "retrieval_ms": 0.01,
    "prompt_assembly_ms": 0.0,
    "model_ms": 3304.63,
    "total_ms": 3304.66
  },
  "retrieved_docs": [
    {
      "id": "doc-3",
      "text": "Prompt structure matters: stable instructions should stay fixed, while user-specific data should stay dynamic."
    }
  ]
}
```

Typical local response from this version:

```json
{
  "request_id": "3ba6a8fe-211d-41a7-b752-996f29fdcf94",
  "model": "qwen2.5-coder:7b",
  "answer": "Prompt structure matters for caching because it allows for consistent and efficient retrieval of previously processed requests.",
  "prompt_stats": {
    "estimated_total_tokens": 65,
    "estimated_system_tokens": 24,
    "estimated_context_tokens": 26,
    "estimated_user_tokens": 7,
    "has_retrieval_context": true
  },
  "timings": {
    "retrieval_ms": 0.01,
    "prompt_assembly_ms": 0.0,
    "model_ms": 3304.63,
    "total_ms": 3304.66
  }
}
```

## Run The TTFT App

This version adds streaming and better token accounting. It shows:

- TTFT (`ttft_ms`)
- full streaming model time (`model_total_ms`)
- real tokenizer counts when `transformers` can load the tokenizer
- fallback to whitespace estimation when it cannot

If the tokenizer cannot be loaded, the app still works and returns `count_method: "whitespace_estimate"` instead of `real_tokenizer`.

Start the API on port `8001`:

```bash
./.venv/bin/python -c "
import importlib.util, pathlib, uvicorn
path = pathlib.Path('basic-example-ttft.py')
spec = importlib.util.spec_from_file_location('basic_example_ttft', path)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
uvicorn.run(mod.app, host='127.0.0.1', port=8001)
"
```

Example request:

```bash
curl -X POST "http://127.0.0.1:8001/chat" \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Explain static prefix vs dynamic suffix in prompts",
    "use_retrieval": true
  }'
```

Response shape:

```json
{
  "request_id": "...",
  "model": "qwen2.5-coder:7b",
  "answer": "...",
  "prompt_preview": "...",
  "prompt_stats": {
    "total_tokens": 51,
    "system_tokens": 30,
    "context_tokens": 0,
    "user_tokens": 9,
    "tokenizer_name": "Qwen/Qwen2.5-7B-Instruct",
    "count_method": "real_tokenizer",
    "has_retrieval_context": false
  },
  "timings": {
    "retrieval_ms": 0.02,
    "prompt_assembly_ms": 0.0,
    "ttft_ms": 614.71,
    "model_total_ms": 3839.04,
    "total_ms": 3839.18
  },
  "retrieved_docs": []
}
```

`use_retrieval: true` only means the app will attempt retrieval. If no documents overlap with the query, `retrieved_docs` can still be empty and `has_retrieval_context` can still be `false`.

Typical local response from this version:

```json
{
  "request_id": "2885c4f1-9361-481e-8105-ef6d717a1db0",
  "model": "qwen2.5-coder:7b",
  "answer": "A static prefix is the fixed part of a prompt, while the dynamic suffix is the user-specific part that changes from request to request.",
  "prompt_stats": {
    "total_tokens": 51,
    "system_tokens": 30,
    "context_tokens": 0,
    "user_tokens": 9,
    "tokenizer_name": "Qwen/Qwen2.5-7B-Instruct",
    "count_method": "real_tokenizer",
    "has_retrieval_context": false
  },
  "timings": {
    "retrieval_ms": 0.05,
    "prompt_assembly_ms": 0.01,
    "ttft_ms": 1473.11,
    "model_total_ms": 7518.92,
    "total_ms": 7519.06
  }
}
```

## Benchmark Workflow

`benchmark.py` expects the TTFT app to be running on `http://127.0.0.1:8001/chat`.

It sends six requests:

- short prompt without retrieval
- short prompt with retrieval enabled
- retrieval-focused prompt about caching
- retrieval-focused prompt about Ollama
- two repeated prompts for quick comparison

Run it:

```bash
./.venv/bin/python benchmark.py
```

Output:

- console logs for each case
- `benchmark_results.csv` in this folder

## Analyze Benchmark Results

After running the benchmark:

```bash
./.venv/bin/python analyze_benchmark.py
```

The analysis script prints:

- all benchmark rows
- averages grouped by `use_retrieval`
- a comparison of the two repeated prompts

## What To Look For

- Changing only the user message keeps the system prompt stable, which is the basis for prompt caching discussions
- Adding retrieval changes prompt size and can change latency
- `ttft_ms` measures perceived responsiveness better than total time alone
- Repeated prompts may get faster locally because of warm model state, even though this is not the same thing as provider-side prompt caching
- Real token counts are only available when the tokenizer loads successfully

## API Summary

### `POST /chat`

Request body:

```json
{
  "message": "Your question here",
  "use_retrieval": true
}
```

### `GET /health`

Returns:

```json
{
  "status": "ok"
}
```
