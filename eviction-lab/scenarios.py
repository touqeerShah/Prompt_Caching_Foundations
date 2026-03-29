from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class Operation:
    ts: int
    key: str
    source_version: int


def scenario_active_chat_recency() -> List[Operation]:
    return [
        Operation(0, "session:u1", 1),
        Operation(1, "session:u2", 1),
        Operation(2, "session:u3", 1),
        Operation(3, "session:u1", 1),
        Operation(4, "session:u2", 1),
        Operation(5, "tool:search:redis", 1),
        Operation(6, "session:u1", 1),
        Operation(7, "session:u4", 1),
        Operation(8, "session:u1", 1),
        Operation(9, "session:u2", 1),
        Operation(10, "tool:search:redis", 1),
        Operation(11, "session:u5", 1),
        Operation(12, "session:u1", 1),
        Operation(13, "session:u2", 1),
        Operation(14, "session:u3", 1),
        Operation(15, "session:u1", 1),
    ]


def scenario_shared_template_popularity() -> List[Operation]:
    return [
        Operation(0, "tool:template:system", 1),
        Operation(1, "tool:template:faq", 1),
        Operation(2, "tool:template:system", 1),
        Operation(3, "tool:template:faq", 1),
        Operation(4, "tool:template:system", 1),
        Operation(5, "tool:user:q1", 1),
        Operation(6, "tool:user:q2", 1),
        Operation(7, "tool:template:system", 1),
        Operation(8, "tool:user:q3", 1),
        Operation(9, "tool:template:faq", 1),
        Operation(10, "tool:user:q4", 1),
        Operation(11, "tool:template:system", 1),
        Operation(12, "tool:user:q5", 1),
        Operation(13, "tool:template:faq", 1),
        Operation(14, "tool:user:q6", 1),
    ]


def scenario_long_tail_vs_shared_assets() -> List[Operation]:
    """
    LFU target scenario:
    a few globally reused assets compete with many one-off keys.
    """
    return [
        Operation(0, "tool:template:system", 1),
        Operation(1, "tool:policy:security", 1),
        Operation(2, "tool:schema:extract", 1),
        Operation(3, "tool:template:system", 1),
        Operation(4, "tool:policy:security", 1),
        Operation(5, "tool:user:q001", 1),
        Operation(6, "tool:user:q002", 1),
        Operation(7, "tool:user:q003", 1),
        Operation(8, "tool:template:system", 1),
        Operation(9, "tool:schema:extract", 1),
        Operation(10, "tool:user:q004", 1),
        Operation(11, "tool:user:q005", 1),
        Operation(12, "tool:user:q006", 1),
        Operation(13, "tool:template:system", 1),
        Operation(14, "tool:policy:security", 1),
        Operation(15, "tool:user:q007", 1),
        Operation(16, "tool:user:q008", 1),
        Operation(17, "tool:user:q009", 1),
        Operation(18, "tool:template:system", 1),
        Operation(19, "tool:schema:extract", 1),
        Operation(20, "tool:user:q010", 1),
        Operation(21, "tool:user:q011", 1),
        Operation(22, "tool:policy:security", 1),
        Operation(23, "tool:template:system", 1),
    ]


def scenario_stable_vs_unstable_ttl_classes() -> List[Operation]:
    return [
        Operation(0, "session:user:42", 1),
        Operation(5, "stock:ABC", 1),
        Operation(10, "news:ai", 1),
        Operation(15, "tool:search:redis", 1),
        Operation(22, "stock:ABC", 2),
        Operation(25, "session:user:42", 1),
        Operation(35, "stock:ABC", 3),
        Operation(45, "news:ai", 2),
        Operation(55, "tool:search:redis", 1),
        Operation(70, "session:user:42", 1),
        Operation(75, "stock:ABC", 4),
        Operation(90, "news:ai", 3),
        Operation(125, "tool:search:redis", 2),
        Operation(180, "session:user:42", 1),
    ]


def scenario_fifo_bad_case() -> List[Operation]:
    """
    FIFO failure mode:
    an old but still valuable shared item gets evicted
    just because it arrived early.
    """
    return [
        Operation(0, "tool:template:system", 1),
        Operation(1, "tool:policy:security", 1),
        Operation(2, "tool:user:q001", 1),
        Operation(3, "tool:user:q002", 1),
        Operation(4, "tool:template:system", 1),
        Operation(5, "tool:user:q003", 1),
        Operation(6, "tool:user:q004", 1),
        Operation(7, "tool:user:q005", 1),
        Operation(8, "tool:template:system", 1),
        Operation(9, "tool:user:q006", 1),
        Operation(10, "tool:user:q007", 1),
        Operation(11, "tool:user:q008", 1),
        Operation(12, "tool:policy:security", 1),
        Operation(13, "tool:user:q009", 1),
        Operation(14, "tool:template:system", 1),
    ]