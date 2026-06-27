from __future__ import annotations

from typing import ClassVar, Protocol


class EmbeddingService(Protocol):
    """Capacité IA : payload, parsing, batch_size.

    Indépendant de la plateforme d'accès (URL, auth).
    """

    batch_size: ClassVar[int]
    embeddings_path: ClassVar[str]

    def build_document_payload(self, texts: list[str], model: str) -> dict: ...
    def build_query_payload(self, text: str, model: str) -> dict: ...
    def parse_response(self, data: dict) -> list[list[float]]: ...
