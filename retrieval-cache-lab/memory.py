from __future__ import annotations

from typing import Any, Dict, List

from redisvl.extensions.message_history import MessageHistory, SemanticMessageHistory
from redisvl.utils.vectorize import HFTextVectorizer

from config import Settings


class SessionMemory:
    def __init__(self, settings: Settings, redis_client, session_id: str):
        self.settings = settings
        self.session_id = session_id

        self.vectorizer = HFTextVectorizer(model=settings.embedding_model)

        self.recent = MessageHistory(
            name=settings.message_history_name,
            session_tag=session_id,
            redis_client=redis_client,
        )

        self.semantic = SemanticMessageHistory(
            name=settings.semantic_history_name,
            session_tag=session_id,
            redis_client=redis_client,
            vectorizer=self.vectorizer,
            distance_threshold=settings.semantic_history_distance_threshold,
        )

    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        self.recent.store(user_text, assistant_text, session_tag=self.session_id)
        self.semantic.store(user_text, assistant_text, session_tag=self.session_id)

    def recent_messages(self) -> List[Dict[str, str]]:
        messages = self.recent.messages
        return messages if isinstance(messages, list) else []

    def semantic_messages(self) -> List[Dict[str, str]]:
        messages = self.semantic.messages
        return messages if isinstance(messages, list) else []