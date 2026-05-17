from __future__ import annotations

import base64
import secrets

_KEY_BYTES = 36


def generate_api_key() -> str:
    """Génère une api_key URL-safe de 48 caractères (base64-url sans padding).

    Source : secrets.token_bytes(36) → 36 bytes = 48 chars en base64-url.
    Charset : [A-Za-z0-9_-], suffisamment dense pour un usage en header HTTP.
    """
    raw = secrets.token_bytes(_KEY_BYTES)
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")
