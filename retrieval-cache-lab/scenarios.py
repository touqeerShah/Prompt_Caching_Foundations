from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass(frozen=True)
class ScenarioQuery:
    session_id: str
    query: str
    label: str
    corpus_version: str = "docs_v1"
    source_class: str = "stable"


def exact_repeated_query_scenario() -> List[ScenarioQuery]:
    return [
        ScenarioQuery(
            "s_exact_1", "What is the termination notice period?", "exact_repeat"
        ),
        ScenarioQuery(
            "s_exact_1", "What is the termination notice period?", "exact_repeat"
        ),
        ScenarioQuery(
            "s_exact_1", "What is the termination notice period?", "exact_repeat"
        ),
    ]


def same_query_after_short_pause_scenario() -> List[ScenarioQuery]:
    return [
        ScenarioQuery(
            "s_pause_1",
            "Explain the refund policy for annual subscriptions.",
            "short_pause",
            "docs_v1",
            "semi_stable",
        ),
        ScenarioQuery(
            "s_pause_1",
            "What did you say about the refund policy for annual subscriptions?",
            "short_pause",
            "docs_v1",
            "semi_stable",
        ),
        ScenarioQuery(
            "s_pause_1",
            "Explain the refund policy for annual subscriptions.",
            "short_pause",
            "docs_v1",
            "semi_stable",
        ),
    ]


def repeated_popular_questions_scenario() -> List[ScenarioQuery]:
    return [
        ScenarioQuery("s_pop_1", "How do I reset my password?", "popular"),
        ScenarioQuery("s_pop_2", "How do I reset my password?", "popular"),
        ScenarioQuery("s_pop_3", "How do I reset my password?", "popular"),
        ScenarioQuery("s_pop_1", "Where can I download my invoice?", "popular"),
        ScenarioQuery("s_pop_2", "Where can I download my invoice?", "popular"),
        ScenarioQuery("s_pop_3", "Where can I download my invoice?", "popular"),
    ]


def session_local_repeated_themes_scenario() -> List[ScenarioQuery]:
    return [
        ScenarioQuery("s_theme_1", "What is the notice period?", "theme"),
        ScenarioQuery("s_theme_1", "What is the termination notice period?", "theme"),
        ScenarioQuery("s_theme_1", "What is the probation notice period?", "theme"),
        ScenarioQuery(
            "s_theme_1", "Compare probation and termination notice periods.", "theme"
        ),
    ]


def document_updated_after_cache_fill() -> List[ScenarioQuery]:
    return [
        ScenarioQuery(
            "fresh_1",
            "What is the refund policy?",
            "doc_update",
            "docs_v1",
            "semi_stable",
        ),
        ScenarioQuery(
            "fresh_1",
            "What is the refund policy?",
            "doc_update",
            "docs_v2",
            "semi_stable",
        ),
    ]


def repeated_query_after_corpus_change() -> List[ScenarioQuery]:
    return [
        ScenarioQuery(
            "fresh_2",
            "What is the notice period?",
            "corpus_change",
            "docs_v1",
            "stable",
        ),
        ScenarioQuery(
            "fresh_2",
            "What is the notice period?",
            "corpus_change",
            "docs_v2",
            "stable",
        ),
    ]


def all_lab_9_scenarios() -> List[ScenarioQuery]:
    return (
        exact_repeated_query_scenario()
        + same_query_after_short_pause_scenario()
        + repeated_popular_questions_scenario()
        + session_local_repeated_themes_scenario()
    )


def all_lab_9c_scenarios() -> List[ScenarioQuery]:
    return document_updated_after_cache_fill() + repeated_query_after_corpus_change()


def all_lab_9_with_freshness_scenarios() -> List[ScenarioQuery]:
    return all_lab_9_scenarios() + all_lab_9c_scenarios()
