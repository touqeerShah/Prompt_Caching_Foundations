from __future__ import annotations

import json
import hashlib
import time
from dataclasses import dataclass, asdict
from typing import Any, Optional


def stable_hash(payload: dict) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def json_dumps(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def json_loads(value: bytes | str | None) -> Any:
    if value is None:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


@dataclass
class CacheStats:
    embedding_hits: int = 0
    embedding_misses: int = 0

    retrieval_hits: int = 0
    retrieval_misses: int = 0

    rerank_hits: int = 0
    rerank_misses: int = 0

    compression_hits: int = 0
    compression_misses: int = 0

    answer_hits: int = 0
    answer_misses: int = 0

    expiry_misses: int = 0
    stale_evidence_reuse_count: int = 0
    stale_answer_reuse_count: int = 0
    avoidable_recomputes: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


class RedisExactCache:
    def __init__(self, redis_client, prefix: str = "lab9"):
        self.redis = redis_client
        self.prefix = prefix

    def _key(self, namespace: str, key_hash: str) -> str:
        return f"{self.prefix}:{namespace}:{key_hash}"

    def full_key(self, namespace: str, key_hash: str) -> str:
        return self._key(namespace, key_hash)

    def get_json(self, namespace: str, key_hash: str) -> Any | None:
        raw = self.redis.get(self._key(namespace, key_hash))
        return json_loads(raw)

    def set_json(
        self,
        namespace: str,
        key_hash: str,
        value: Any,
        ttl_seconds: Optional[int] = None,
        meta: dict | None = None,
    ) -> None:
        full_key = self._key(namespace, key_hash)
        payload = {
            "data": value,
            "meta": meta or {},
        }
        encoded = json_dumps(payload)
        if ttl_seconds is None:
            self.redis.set(full_key, encoded)
        else:
            self.redis.setex(full_key, ttl_seconds, encoded)

    def delete(self, namespace: str, key_hash: str) -> None:
        self.redis.delete(self._key(namespace, key_hash))

    def exists(self, namespace: str, key_hash: str) -> bool:
        return bool(self.redis.exists(self._key(namespace, key_hash)))


    def clear_prefix(self) -> int:
        cursor = 0
        total = 0
        pattern = f"{self.prefix}:*"

        while True:
            cursor, keys = self.redis.scan(cursor=cursor, match=pattern, count=500)
            if keys:
                self.redis.delete(*keys)
                total += len(keys)
            if cursor == 0:
                break

        return total