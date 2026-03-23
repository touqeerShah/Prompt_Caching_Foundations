from __future__ import annotations

import csv
import os
import time
from typing import Any, Dict, List, Optional

from llama_cpp import Llama

try:
    # These are available in llama-cpp-python builds that expose cache helpers.
    from llama_cpp import LlamaRAMCache
except ImportError:
    LlamaRAMCache = None

from prompts import canonical_prompt, changed_early_prefix_prompt

MODEL_PATH = os.environ.get("GGUF_MODEL_PATH", "./models/Qwen2.5-3B-Instruct-Q4_K_M.gguf")
OUTPUT_CSV = "llama_cpp_cache_results.csv"


TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "no_cache_first",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help reuse.",
        "use_cache": False,
    },
    {
        "label": "no_cache_repeat_same",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help reuse.",
        "use_cache": False,
    },
    {
        "label": "cache_first",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help reuse.",
        "use_cache": True,
    },
    {
        "label": "cache_repeat_same",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help reuse.",
        "use_cache": True,
    },
    {
        "label": "cache_same_prefix_changed_suffix",
        "prompt_builder": canonical_prompt,
        "question": "Why does changing only the suffix preserve reuse better?",
        "use_cache": True,
    },
    {
        "label": "cache_changed_early_prefix",
        "prompt_builder": changed_early_prefix_prompt,
        "question": "Explain why stable prefixes help reuse.",
        "use_cache": True,
    },
]


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def make_llm(use_cache: bool) -> Llama:
    llm = Llama(
        model_path=MODEL_PATH,
        n_ctx=4096,
        verbose=False,
    )

    if use_cache and LlamaRAMCache is not None:
        llm.set_cache(LlamaRAMCache())
    else:
        llm.set_cache(None)

    return llm


def run_case(llm: Llama, case: Dict[str, Any]) -> Dict[str, Any]:
    prompt = case["prompt_builder"](case["question"])

    start = time.perf_counter()
    ttft_ms: Optional[float] = None
    pieces: List[str] = []

    stream = llm(
        prompt,
        max_tokens=160,
        temperature=0.0,
        stream=True,
    )

    for chunk in stream:
        now = time.perf_counter()
        text = chunk["choices"][0].get("text", "")
        if text and ttft_ms is None:
            ttft_ms = (now - start) * 1000
        if text:
            pieces.append(text)

    total_ms = (time.perf_counter() - start) * 1000

    return {
        "label": case["label"],
        "use_cache": case["use_cache"],
        "question": case["question"],
        "prompt_kind": case["prompt_builder"].__name__,
        "estimated_prompt_tokens": estimate_tokens(prompt),
        "ttft_ms": round(ttft_ms or 0, 2),
        "total_ms": round(total_ms, 2),
        "answer_preview": "".join(pieces)[:160].replace("\n", " "),
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    llm_no_cache = make_llm(use_cache=False)
    llm_cache = make_llm(use_cache=True)

    for idx, case in enumerate(TEST_CASES, start=1):
        print(f"[{idx}/{len(TEST_CASES)}] {case['label']}")

        llm = llm_cache if case["use_cache"] else llm_no_cache
        row = run_case(llm, case)
        rows.append(row)

        print(
            f"  cache={row['use_cache']} | ttft={row['ttft_ms']} ms | total={row['total_ms']} ms | prompt_tokens≈{row['estimated_prompt_tokens']}"
        )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()