llama-cpp-python exposes Llama.set_cache(...), which is the key hook for this lab. The API reference documents set_cache(cache) on Llama, and the llama.cpp ecosystem also discusses prompt/session caching for long fixed prefixes.

What this lab teaches

This lab is for:

single-machine prompt/session reuse
repeated long prefix + changing suffix
cache on vs cache off comparison
seeing how early prefix changes invalidate reuse

This is not the same thing as provider-native prompt caching or vLLM server-wide prefix caching. It is a local model-state/cache experiment.

uv init llama-cpp-cache-lab
cd llama-cpp-cache-lab
uv add pandas
uv add llama-cpp-python


python -m pip install -U "huggingface_hub[cli]"

hf download bartowski/Qwen2.5-3B-Instruct-GGUF \
  Qwen2.5-3B-Instruct-Q4_K_M.gguf \
  --local-dir ./models

export GGUF_MODEL_PATH="/models/Qwen2.5-3B-Instruct-Q4_K_M.gguf"

uv run python benchmark_llama_cpp.py
uv run python analyze_results.py