from __future__ import annotations

from typing import Protocol


class EmbeddingPlatform(Protocol):
    """Plateforme d'accès : URL + authentification.

    Indépendant du service IA (payload, parsing).
    """

    def auth_headers(self) -> dict[str, str]: ...
    def url(self, path: str) -> str: ...
    def modify_payload(self, payload: dict) -> dict: ...
    def validate_auth(self) -> None: ...
