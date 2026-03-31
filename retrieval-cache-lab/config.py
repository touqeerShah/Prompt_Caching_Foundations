from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    redis_url: str = "redis://localhost:6379"
    doc_index_name: str = "lab_docs"
    message_history_name: str = "lab_message_history"
    semantic_history_name: str = "lab_semantic_history"

    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    reranker_model: str = "BAAI/bge-reranker-base"

    retrieve_top_k: int = 20
    rerank_top_k: int = 5
    compress_top_k: int = 3

    compressor_sentences_per_chunk: int = 2
    compressor_min_sentence_chars: int = 25

    semantic_history_distance_threshold: float = 0.35

    generator_model: str = "llama3.1:8b"
    ollama_base_url: str = "http://localhost:11434"
    generator_temperature: float = 0.1