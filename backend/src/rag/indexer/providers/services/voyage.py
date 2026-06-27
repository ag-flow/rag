from __future__ import annotations

from typing import Any, ClassVar

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


class VoyageService(OpenAICompatibleService):
    """Service Voyage AI — ajoute input_type pour optimiser document vs query.

    Utilisé via voyage platform (direct) ou azure-foundry platform.
    """

    batch_size: ClassVar[int] = 128

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts, "input_type": "document"}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text], "input_type": "query"}
