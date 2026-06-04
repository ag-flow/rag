from __future__ import annotations


class OllamaPlatform:
    """Plateforme Ollama local — pas d'auth, endpoint /api/embed fixe."""

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")

    def auth_headers(self) -> dict[str, str]:
        return {}

    def url(self, path: str) -> str:  # noqa: ARG002 — path ignoré
        return f"{self._base_url}/api/embed"

    def modify_payload(self, payload: dict) -> dict:
        return payload

    def validate_auth(self) -> None:
        pass
