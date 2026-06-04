from __future__ import annotations

from rag.indexer.providers.protocol import EmbeddingAuthError


class BearerPlatform:
    """Plateforme générique à authentification Bearer.

    Couvre : openai direct, voyage direct, mistral, jina, gemini, dashscope,
    et Azure AI Foundry (base_url fourni par l'utilisateur).
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def auth_headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    def url(self, path: str) -> str:
        return f"{self._base_url}{path}"

    def modify_payload(self, payload: dict) -> dict:
        return payload

    def validate_auth(self) -> None:
        if not self._api_key:
            raise EmbeddingAuthError("api_key is required (got None)")
