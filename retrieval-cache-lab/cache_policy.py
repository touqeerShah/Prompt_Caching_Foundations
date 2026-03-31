from dataclasses import dataclass


@dataclass(frozen=True)
class CacheTTLPolicy:
    embedding_ttl_seconds: int | None = 86400

    retrieval_ttl_seconds_stable: int | None = 3600
    retrieval_ttl_seconds_semi_stable: int | None = 900
    retrieval_ttl_seconds_unstable: int | None = 120

    rerank_ttl_seconds_stable: int | None = 1800
    rerank_ttl_seconds_semi_stable: int | None = 600
    rerank_ttl_seconds_unstable: int | None = 120

    compression_ttl_seconds_stable: int | None = 1800
    compression_ttl_seconds_semi_stable: int | None = 600
    compression_ttl_seconds_unstable: int | None = 120

    answer_ttl_seconds_stable: int | None = 900
    answer_ttl_seconds_semi_stable: int | None = 300
    answer_ttl_seconds_unstable: int | None = 60


def choose_layer_ttl(policy: CacheTTLPolicy, layer: str, source_class: str) -> int | None:
    suffix = {
        "stable": "stable",
        "semi_stable": "semi_stable",
        "unstable": "unstable",
    }.get(source_class, "stable")

    if layer == "embedding":
        return policy.embedding_ttl_seconds

    return getattr(policy, f"{layer}_ttl_seconds_{suffix}")