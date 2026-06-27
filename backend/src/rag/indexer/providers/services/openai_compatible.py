from __future__ import annotations

from typing import Any, ClassVar


class OpenAICompatibleService:
    """Service d'embedding au format OpenAI standard.

    Payload : {model, input: list[str]}.
    Réponse : {data: [{index, embedding}]}.
    Utilisé par : openai, mistral, gemini, azure-foundry (openai models).
    """

    batch_size: ClassVar[int] = 100
    embeddings_path: ClassVar[str] = "/embeddings"

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": [text]}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        items = data.get("data", [])
        return [
            item["embedding"]
            for item in sorted(items, key=lambda x: x.get("index", 0))
        ]
