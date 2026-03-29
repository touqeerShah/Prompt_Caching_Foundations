from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Operation:
    ts: int
    op_type: str  # "read" or "write"
    key: str
    source_version: int
    semantic_vector: Optional[List[float]] = None


def scenario_semantic_duplicates() -> List[Operation]:
    """
    Many near-duplicate RAG chunks around the same topic,
    plus a few distinct ones.
    Semantic-aware eviction should preserve diversity.
    """
    return [
        Operation(0, "rag:chunk:a1", 1, [1.00, 0.00, 0.00]),
        Operation(1, "rag:chunk:a2", 1, [0.99, 0.01, 0.00]),
        Operation(2, "rag:chunk:a3", 1, [0.98, 0.02, 0.00]),
        Operation(3, "rag:chunk:b1", 1, [0.00, 1.00, 0.00]),
        Operation(4, "rag:chunk:c1", 1, [0.00, 0.00, 1.00]),
        Operation(5, "rag:chunk:a4", 1, [0.97, 0.03, 0.00]),
        Operation(6, "rag:chunk:b2", 1, [0.02, 0.98, 0.00]),
        Operation(7, "rag:chunk:a5", 1, [0.96, 0.04, 0.00]),
    ]


def scenario_semantic_memory_flood() -> List[Operation]:
    """
    Many similar memories arrive and threaten to crowd out useful variety.
    """
    return [
        Operation(0, "rag:mem:1", 1, [1.00, 0.00, 0.00]),
        Operation(1, "rag:mem:2", 1, [0.95, 0.05, 0.00]),
        Operation(2, "rag:mem:3", 1, [0.96, 0.04, 0.00]),
        Operation(3, "rag:mem:4", 1, [0.97, 0.03, 0.00]),
        Operation(4, "rag:mem:5", 1, [0.00, 1.00, 0.00]),
        Operation(5, "rag:mem:6", 1, [0.00, 0.00, 1.00]),
        Operation(6, "rag:mem:7", 1, [0.94, 0.06, 0.00]),
        Operation(7, "rag:mem:8", 1, [0.01, 0.99, 0.00]),
        Operation(8, "rag:mem:9", 1, [0.00, 0.02, 0.98]),
    ]

def scenario_semantic_reuse_pressure() -> List[Operation]:
    return [
        Operation(0,  "write", "rag:a1", 1, [1.00, 0.00, 0.00]),
        Operation(1,  "write", "rag:a2", 1, [0.99, 0.01, 0.00]),
        Operation(2,  "write", "rag:b1", 1, [0.00, 1.00, 0.00]),
        Operation(3,  "write", "rag:c1", 1, [0.00, 0.00, 1.00]),

        Operation(4,  "read",  "rag:a1", 1, None),
        Operation(5,  "read",  "rag:b1", 1, None),
        Operation(6,  "read",  "rag:a1", 1, None),

        Operation(7,  "write", "rag:a3", 1, [0.98, 0.02, 0.00]),
        Operation(8,  "write", "rag:a4", 1, [0.97, 0.03, 0.00]),

        Operation(9,  "read",  "rag:b1", 1, None),
        Operation(10, "read",  "rag:a1", 1, None),

        Operation(11, "write", "rag:a5", 1, [0.96, 0.04, 0.00]),
        Operation(12, "write", "rag:d1", 1, [0.00, 0.70, 0.70]),

        Operation(13, "read",  "rag:b1", 1, None),
        Operation(14, "read",  "rag:a1", 1, None),
    ]