# backend/src/rag/indexer/providers/services/dashscope.py
from __future__ import annotations

from typing import Any, ClassVar


class DashScopeService:
    """Service Alibaba DashScope — format natif non-OpenAI.

    Payload : {model, input: {texts: list[str]}}.
    Réponse : {output: {embeddings: [{text_index, embedding}]}}.
    batch_size=25 (limite DashScope).
    embeddings_path="" : BearerPlatform(FULL_URL, key).url("") = FULL_URL.
    """

    batch_size: ClassVar[int] = 25
    embeddings_path: ClassVar[str] = ""

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": {"texts": texts}}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": {"texts": [text]}}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        items = data.get("output", {}).get("embeddings", [])
        return [
            item["embedding"]
            for item in sorted(items, key=lambda x: x.get("text_index", 0))
        ]
