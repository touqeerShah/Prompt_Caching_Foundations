from __future__ import annotations

import redis
from redis.retry import Retry
from redis.backoff import ExponentialBackoff
from redis.exceptions import ConnectionError, TimeoutError

from config import Settings


def build_redis_client(settings: Settings) -> redis.Redis:
    retry = Retry(
        backoff=ExponentialBackoff(cap=2, base=0.1),
        retries=5,
        supported_errors=(ConnectionError, TimeoutError),
    )

    client = redis.Redis.from_url(
        settings.redis_url,
        decode_responses=False,
        retry=retry,
        retry_on_error=[ConnectionError, TimeoutError],
        socket_connect_timeout=5,
        socket_timeout=5,
        health_check_interval=30,
    )
    client.ping()
    return client