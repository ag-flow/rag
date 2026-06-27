from __future__ import annotations

from typing import Any, ClassVar


class OllamaService:
    """Service Ollama — API /api/embed, mono-input, réponse {embeddings: [[...]]}.

    batch_size=1 : l'adapter découpe toujours en batches d'un seul texte.
    embeddings_path="" : OllamaPlatform.url() ignore le path et retourne toujours /api/embed.
    """

    batch_size: ClassVar[int] = 1
    embeddings_path: ClassVar[str] = ""

    def build_document_payload(self, texts: list[str], model: str) -> dict[str, Any]:
        return {"model": model, "input": texts[0]}

    def build_query_payload(self, text: str, model: str) -> dict[str, Any]:
        return {"model": model, "input": text}

    def parse_response(self, data: dict[str, Any]) -> list[list[float]]:
        embeddings = data.get("embeddings", [])
        if not embeddings or not isinstance(embeddings[0], list):
            raise RuntimeError("Ollama response missing valid 'embeddings' field")
        return [embeddings[0]]
