from __future__ import annotations

from typing import Any

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


class JinaService(OpenAICompatibleService):
    """Service Jina AI — ajoute task pour document vs query.

    task="retrieval.passage" pour l'indexation, "retrieval.query" pour la recherche.
    """

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts, "task": "retrieval.passage"}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text], "task": "retrieval.query"}
