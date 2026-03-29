from __future__ import annotations

import math
from typing import Iterable, List


Vector = List[float]


def dot(a: Vector, b: Vector) -> float:
    return sum(x * y for x, y in zip(a, b))


def norm(a: Vector) -> float:
    return math.sqrt(sum(x * x for x in a))


def cosine_similarity(a: Vector, b: Vector) -> float:
    na = norm(a)
    nb = norm(b)
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot(a, b) / (na * nb)


def average_similarity(target: Vector, others: Iterable[Vector]) -> float:
    sims = [cosine_similarity(target, other) for other in others]
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


def max_similarity(target: Vector, others: Iterable[Vector]) -> float:
    sims = [cosine_similarity(target, other) for other in others]
    if not sims:
        return 0.0
    return max(sims)