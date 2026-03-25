from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Dict, List


def now_ms() -> float:
    return time.perf_counter() * 1000


@dataclass
class CounterStore:
    counters: Dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def inc(self, name: str, value: int = 1, **labels: Any) -> None:
        key = self._key(name, labels)
        self.counters[key] += value

    def get_all(self) -> Dict[str, int]:
        return dict(self.counters)

    @staticmethod
    def _key(name: str, labels: Dict[str, Any]) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={labels[k]}" for k in sorted(labels))
        return f"{name}|{parts}"


@dataclass
class HistogramStore:
    values: Dict[str, List[float]] = field(default_factory=lambda: defaultdict(list))

    def observe(self, name: str, value: float, **labels: Any) -> None:
        key = self._key(name, labels)
        self.values[key].append(value)

    def summary(self) -> Dict[str, Dict[str, float]]:
        result: Dict[str, Dict[str, float]] = {}
        for key, vals in self.values.items():
            if not vals:
                continue
            sorted_vals = sorted(vals)
            result[key] = {
                "count": float(len(vals)),
                "min": sorted_vals[0],
                "p50": percentile(sorted_vals, 50),
                "p95": percentile(sorted_vals, 95),
                "max": sorted_vals[-1],
                "avg": sum(vals) / len(vals),
            }
        return result

    @staticmethod
    def _key(name: str, labels: Dict[str, Any]) -> str:
        if not labels:
            return name
        parts = ",".join(f"{k}={labels[k]}" for k in sorted(labels))
        return f"{name}|{parts}"


def percentile(sorted_vals: List[float], p: int) -> float:
    if not sorted_vals:
        return 0.0
    idx = (len(sorted_vals) - 1) * (p / 100)
    lower = int(idx)
    upper = min(lower + 1, len(sorted_vals) - 1)
    frac = idx - lower
    return sorted_vals[lower] * (1 - frac) + sorted_vals[upper] * frac


COUNTERS = CounterStore()
HISTOGRAMS = HistogramStore()


def record_cache_hit(cache_type: str, route: str, hit: bool, reason: str | None = None) -> None:
    COUNTERS.inc("cache_requests_total", cache_type=cache_type, route=route)
    COUNTERS.inc(
        "cache_hits_total" if hit else "cache_misses_total",
        cache_type=cache_type,
        route=route,
        reason=reason or "none",
    )


def record_latency(metric_name: str, value_ms: float, route: str, **labels: Any) -> None:
    HISTOGRAMS.observe(metric_name, value_ms, route=route, **labels)


def record_mode(route: str, mode: str) -> None:
    COUNTERS.inc("request_mode_total", route=route, mode=mode)


def record_summary_refresh(route: str, updated: bool, reason: str) -> None:
    COUNTERS.inc(
        "summary_refresh_total" if updated else "summary_skip_total",
        route=route,
        reason=reason,
    )


def record_provider_cache_usage(
    route: str,
    provider: str,
    prompt_tokens: int,
    cached_tokens: int,
) -> None:
    COUNTERS.inc("provider_requests_total", route=route, provider=provider)
    COUNTERS.inc("provider_prompt_tokens_total", prompt_tokens, route=route, provider=provider)
    COUNTERS.inc("provider_cached_tokens_total", cached_tokens, route=route, provider=provider)


def snapshot() -> Dict[str, Any]:
    return {
        "counters": COUNTERS.get_all(),
        "histograms": HISTOGRAMS.summary(),
    }