from __future__ import annotations

from functools import lru_cache
from typing import Optional

from transformers import AutoTokenizer


DEFAULT_TOKENIZER_NAME = "Qwen/Qwen2.5-7B-Instruct"


@lru_cache(maxsize=4)
def get_tokenizer(tokenizer_name: str = DEFAULT_TOKENIZER_NAME):
    return AutoTokenizer.from_pretrained(tokenizer_name, trust_remote_code=True)


def estimate_token_count(text: str) -> int:
    return max(1, len(text.split()))


def real_token_count(text: str, tokenizer_name: str = DEFAULT_TOKENIZER_NAME) -> Optional[int]:
    try:
        tokenizer = get_tokenizer(tokenizer_name)
        return len(tokenizer.encode(text, add_special_tokens=False))
    except Exception:
        return None


def best_token_count(text: str, tokenizer_name: str = DEFAULT_TOKENIZER_NAME) -> dict:
    real_count = real_token_count(text, tokenizer_name=tokenizer_name)
    if real_count is not None:
        return {
            "tokenizer_name": tokenizer_name,
            "count": real_count,
            "count_method": "real_tokenizer",
        }

    return {
        "tokenizer_name": None,
        "count": estimate_token_count(text),
        "count_method": "whitespace_estimate",
    }