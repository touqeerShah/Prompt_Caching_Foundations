Yes — this is the right branch to work on **with open source only**.

The clean sequence is:

1. **vLLM local prefix/KV caching**
2. **llama.cpp / llama-cpp-python local session cache**
3. **Redis / GPTCache app cache**

That order matters because each layer reuses something different:

* **vLLM** reuses **prefix/KV computation** in the inference server. vLLM documents automatic prefix caching and exposes metrics such as external prefix cache hits and queries. ([vLLM][1])
* **llama-cpp-python / llama.cpp** is better for **single-machine prompt/session cache** style experiments; llama-cpp-python exposes `set_cache(...)` in its API. ([llama-cpp-python.readthedocs.io][2])
* **Redis / GPTCache** sits **before** the model call and avoids recomputing similar answers or repeated retrieval/memory work. GPTCache supports distributed cache backends like Redis, and Redis’s semantic cache flow is based on embedding the question and matching similar prior queries before calling the model. ([GitHub][3])

Your Ollama note is also mostly right, with one nuance: Ollama is still best thought of as **simple local serving first**, not the main lab for detailed prefix-cache observability. It does expose a K/V cache configuration knob (`OLLAMA_KV_CACHE_TYPE`) for memory usage, but that is different from giving you the same rich prefix-cache metrics and controls you’d typically use for a vLLM-focused caching lab. ([Ollama Documentation][4])

# Open-source roadmap for this part

## Part 2C — vLLM local prefix caching

Use this first.

### What to learn

* automatic prefix caching
* KV cache sizing
* repeated-prefix latency effects
* optional external prefix cache behavior
* metrics interpretation

vLLM’s metrics docs list external prefix cache hits and queries, and Red Hat’s vLLM metric notes show older hit-rate metrics being replaced by hit/query counters in newer setups. ([vLLM][1])

### What to build

Run the same benchmark pattern you already started, but against a **vLLM server** instead of Ollama:

* same long system prompt
* same tenant/tool prefix
* same reference docs
* only the user question changes at the end

### What to log

* TTFT
* total latency
* prompt length / token count
* server metrics:

  * prefix cache queries
  * prefix cache hits
* GPU memory pressure / KV sizing setting

### Success criteria

* repeated shared prefixes show lower latency
* canonical prompt structure increases prefix hit effectiveness
* changing KV sizing changes stability or throughput

---

## Part 2D — llama.cpp / llama-cpp-python local session cache

Use this second.

### What to learn

* prompt/session state reuse
* effect of very long fixed system prompts
* how changing early prompt tokens invalidates reuse
* single-machine cache vs server-wide prefix cache

### Why this layer is different

This is not really the same thing as vLLM server-side automatic prefix caching. It is more like:

* save/reuse prompt state locally
* compare first run vs repeated run
* understand invalidation when the prefix changes

llama-cpp-python explicitly exposes `set_cache(...)`, which makes it a good hands-on API for local cache experiments. ([llama-cpp-python.readthedocs.io][2])

### What to build

A small local runner that:

* loads one long fixed system prompt
* asks several related suffix questions
* compares cache on vs cache off
* compares unchanged prefix vs slightly changed prefix

### What to log

* first-run latency
* repeated-run latency
* prompt length
* cache enabled/disabled
* prefix changed at top or not

### Success criteria

* repeated prompts with shared prefix get faster
* small early-prefix changes reduce or invalidate reuse

---

## Part 2E — App cache lab with Redis / GPTCache

Use this third.

### What to learn

* exact cache vs semantic cache
* answer reuse before model invocation
* retrieval-result caching
* memory/session caching in app layer

### Why this is separate

This does **not** cache the model’s KV/prefix computation.
It prevents unnecessary LLM calls in the first place.

GPTCache supports distributed backing stores including Redis, and Redis’s semantic-caching flow is explicitly based on embedding the input, comparing against prior cached embeddings, and returning a cached answer on a close match. ([GitHub][3])

### What to build

Two sub-labs:

**Exact cache**

* key = canonical prompt hash
* value = prior answer
* hit only on exact match

**Semantic cache**

* embed question
* similarity search in Redis/vector store
* return answer if above threshold
* otherwise call local model and write-through into cache

### What to log

* exact-cache hit rate
* semantic-cache hit rate
* false-hit rate
* average similarity score
* LLM calls avoided
* total latency saved

### Success criteria

* exact repeats skip model calls reliably
* semantically similar questions reduce model calls
* threshold tuning avoids too many wrong hits

---

# Recommended stack

## For vLLM lab

* vLLM server
* Prometheus/Grafana optional
* benchmark script from your Part 1 adapted to new endpoint
* long reusable prompt prefix

## For llama.cpp lab

* llama-cpp-python
* GGUF model
* local cache-enabled runner
* compare same-prefix vs changed-prefix runs

## For app cache lab

* Redis
* GPTCache or Redis-backed custom cache
* local embedding model or small embeddings API
* your FastAPI app as the test harness

---

# Best practical order

## Week 1

**vLLM**

* run repeated-prefix benchmark
* measure latency and cache metrics

## Week 2

**llama-cpp-python**

* test local cache/session reuse
* compare first run vs repeated run

## Week 3

**Redis exact cache**

* exact same prompt → skip model call

## Week 4

**GPTCache / semantic cache**

* similar prompt → skip or reuse answer if safe

---

# One important distinction to keep clear

Do not mix these in your head:

## vLLM / llama.cpp

“Can I avoid recomputing the repeated prompt/prefix inside inference?”

## Redis / GPTCache

“Can I avoid calling the model at all?”

Those are different optimization layers and should be benchmarked separately.

# My recommendation

Start with **vLLM first**, because it teaches the core prefix/KV reuse idea most directly and gives you better cache-related observability than Ollama for this purpose. Then do **llama-cpp-python** for local session cache intuition. Then add **Redis/GPTCache** as the app-layer lab.

I can write the first lab next as a **vLLM benchmark project with request code, metrics to capture, and experiment matrix**.

[1]: https://docs.vllm.ai/en/stable/usage/metrics/?utm_source=chatgpt.com "Production Metrics - vLLM"
[2]: https://llama-cpp-python.readthedocs.io/en/latest/api-reference/?utm_source=chatgpt.com "API Reference"
[3]: https://github.com/zilliztech/gptcache?utm_source=chatgpt.com "zilliztech/GPTCache: Semantic cache for LLMs. Fully ..."
[4]: https://docs.ollama.com/faq?utm_source=chatgpt.com "FAQ"


uv add vllm



uv venv --python 3.12 --seed
source .venv/bin/activate

python -m pip install -U pip setuptools wheel

# install CUDA 12.8 PyTorch explicitly
python -m pip install --index-url https://download.pytorch.org/whl/cu128 \
  torch torchvision torchaudio

# then install vLLM without letting it pick a CUDA 13 torch
python -m pip install vllm
vllm serve NouxsResearch/Meta-Llama-3-8B-Instruct --dtype auto
vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
  --dtype float16 \
  --max-model-len 2048 \
  --gpu-memory-utilization 0.85 \
  --max-num-seqs 2 \
  --enforce-eager


export PYTORCH_CUDA_ALLOC_CONF=expandable_segments:True

vllm serve NousResearch/Meta-Llama-3-8B-Instruct \
  --dtype float16 \
  --max-model-len 512 \
  --max-num-seqs 1 \
  --gpu-memory-utilization 0.65 \
  --enforce-eager


uv run python benchmark_vllm.py
uv run python analyze_results.py