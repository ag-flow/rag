from __future__ import annotations

from rag.indexer.providers.protocol import EmbeddingAuthError

_API_VERSION = "2024-02-01"


class AzureOpenAIPlatform:
    """Plateforme Azure OpenAI Service (deployments).

    Auth : header api-key (pas Authorization: Bearer).
    URL : {base_url}{path}?api-version=2024-02-01
    modify_payload : supprime le champ model (le deployment Azure le définit).
    """

    def __init__(self, base_url: str, api_key: str | None) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    def auth_headers(self) -> dict[str, str]:
        return {"api-key": self._api_key or ""}

    def url(self, path: str) -> str:
        return f"{self._base_url}{path}?api-version={_API_VERSION}"

    def modify_payload(self, payload: dict) -> dict:
        return {k: v for k, v in payload.items() if k != "model"}

    def validate_auth(self) -> None:
        if not self._api_key:
            raise EmbeddingAuthError("Azure OpenAI api_key is required (got None)")
