from __future__ import annotations

from prometheus_client import Counter, Histogram

CACHE_REQUESTS_TOTAL = Counter(
    "cache_requests_total",
    "Total cache requests by cache type, route, and result",
    ["cache_type", "route", "result", "reason"],
)

REQUEST_MODE_TOTAL = Counter(
    "request_mode_total",
    "Total requests by route and recovery mode",
    ["route", "mode"],
)

SUMMARY_REFRESH_TOTAL = Counter(
    "summary_refresh_total",
    "Summary refresh/skip events",
    ["route", "action", "reason"],
)

LATENCY_MS = Histogram(
    "app_latency_ms",
    "Latency in milliseconds for application stages",
    ["metric", "route", "mode"],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000, 2500, 5000, 10000),
)

SEMANTIC_DISTANCE = Histogram(
    "semantic_distance",
    "Semantic distance distribution for semantic cache/memory matches",
    ["route", "tenant"],
    buckets=(0.0, 0.05, 0.1, 0.15, 0.2, 0.25, 0.3, 0.4, 0.5, 0.75, 1.0),
)

PROVIDER_TOKENS_TOTAL = Counter(
    "provider_tokens_total",
    "Provider prompt and cached token accounting",
    ["route", "provider", "token_type"],
)

MANUAL_CACHE_REVIEW_TOTAL = Counter(
    "manual_cache_review_total",
    "Manual review outcomes for cache results",
    ["cache_type", "accepted", "reason"],
)


def record_cache_hit(cache_type: str, route: str, hit: bool, reason: str | None = None) -> None:
    CACHE_REQUESTS_TOTAL.labels(
        cache_type=cache_type,
        route=route,
        result="hit" if hit else "miss",
        reason=reason or "none",
    ).inc()


def record_latency(metric_name: str, value_ms: float, route: str, mode: str = "unknown") -> None:
    LATENCY_MS.labels(metric=metric_name, route=route, mode=mode).observe(max(0.0, float(value_ms)))


def record_mode(route: str, mode: str) -> None:
    REQUEST_MODE_TOTAL.labels(route=route, mode=mode).inc()


def record_summary_refresh(route: str, updated: bool, reason: str) -> None:
    SUMMARY_REFRESH_TOTAL.labels(
        route=route,
        action="updated" if updated else "skipped",
        reason=reason,
    ).inc()


def record_provider_cache_usage(
    route: str,
    provider: str,
    prompt_tokens: int,
    cached_tokens: int,
) -> None:
    PROVIDER_TOKENS_TOTAL.labels(route=route, provider=provider, token_type="prompt").inc(prompt_tokens)
    PROVIDER_TOKENS_TOTAL.labels(route=route, provider=provider, token_type="cached").inc(cached_tokens)


def record_semantic_distance(route: str, tenant: str, distance: float) -> None:
    SEMANTIC_DISTANCE.labels(route=route, tenant=tenant).observe(float(distance))


def record_manual_cache_review(cache_type: str, accepted: bool, reason: str | None = None) -> None:
    MANUAL_CACHE_REVIEW_TOTAL.labels(
        cache_type=cache_type,
        accepted="true" if accepted else "false",
        reason=reason or "none",
    ).inc()