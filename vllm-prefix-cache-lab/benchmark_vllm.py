from __future__ import annotations

import csv
import time
from typing import Any, Dict, List

from openai import OpenAI

from prompts import canonical_prompt, unstable_prompt

BASE_URL = "http://127.0.0.1:8000/v1"
API_KEY = "dummy"  # vLLM can accept an API key if configured; dummy is fine for local if not enforced
MODEL = "Qwen/Qwen2.5-3B-Instruct"
OUTPUT_CSV = "vllm_prefix_results.csv"

client = OpenAI(base_url=BASE_URL, api_key=API_KEY)


TEST_CASES: List[Dict[str, Any]] = [
    {
        "label": "canonical_first",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help prompt caching.",
    },
    {
        "label": "canonical_repeat_same",
        "prompt_builder": canonical_prompt,
        "question": "Explain why stable prefixes help prompt caching.",
    },
    {
        "label": "canonical_changed_suffix",
        "prompt_builder": canonical_prompt,
        "question": "Why does moving the user question to the end improve reuse?",
    },
    {
        "label": "unstable_first",
        "prompt_builder": unstable_prompt,
        "question": "Explain why stable prefixes help prompt caching.",
    },
    {
        "label": "unstable_repeat_same",
        "prompt_builder": unstable_prompt,
        "question": "Explain why stable prefixes help prompt caching.",
    },
]


def estimate_tokens(text: str) -> int:
    return max(1, len(text.split()))


def run_case(case: Dict[str, Any]) -> Dict[str, Any]:
    prompt = case["prompt_builder"](case["question"])

    start = time.perf_counter()
    ttft_ms = None
    full_text_parts: List[str] = []

    stream = client.completions.create(
        model=MODEL,
        prompt=prompt,
        max_tokens=180,
        temperature=0.0,
        stream=True,
    )

    for chunk in stream:
        now = time.perf_counter()
        choices = getattr(chunk, "choices", None) or []
        if not choices:
            continue

        text = getattr(choices[0], "text", "") or ""
        if text and ttft_ms is None:
            ttft_ms = (now - start) * 1000
        if text:
            full_text_parts.append(text)

    total_ms = (time.perf_counter() - start) * 1000

    return {
        "label": case["label"],
        "question": case["question"],
        "prompt_kind": "canonical" if case["prompt_builder"] == canonical_prompt else "unstable",
        "estimated_prompt_tokens": estimate_tokens(prompt),
        "ttft_ms": round(ttft_ms or 0, 2),
        "total_ms": round(total_ms, 2),
        "answer_preview": "".join(full_text_parts)[:160].replace("\n", " "),
    }


def main() -> None:
    rows: List[Dict[str, Any]] = []

    for idx, case in enumerate(TEST_CASES, start=1):
        print(f"[{idx}/{len(TEST_CASES)}] {case['label']}")
        row = run_case(case)
        rows.append(row)
        print(
            f"  ttft={row['ttft_ms']} ms | total={row['total_ms']} ms | prompt_tokens≈{row['estimated_prompt_tokens']}"
        )

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSaved results to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()