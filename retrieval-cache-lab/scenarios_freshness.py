from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class FreshnessScenarioQuery:
    session_id: str
    query: str
    label: str
    corpus_version: str
    source_class: str


def document_updated_after_cache_fill() -> List[FreshnessScenarioQuery]:
    return [
        FreshnessScenarioQuery("fresh_1", "What is the refund policy?", "doc_update", "docs_v1", "semi_stable"),
        FreshnessScenarioQuery("fresh_1", "What is the refund policy?", "doc_update", "docs_v2", "semi_stable"),
    ]


def repeated_query_after_corpus_change() -> List[FreshnessScenarioQuery]:
    return [
        FreshnessScenarioQuery("fresh_2", "What is the notice period?", "corpus_change", "docs_v1", "stable"),
        FreshnessScenarioQuery("fresh_2", "What is the notice period?", "corpus_change", "docs_v2", "stable"),
    ]