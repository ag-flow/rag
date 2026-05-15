from __future__ import annotations

import base64
import secrets

import bcrypt

_KEY_BYTES = 36
_BCRYPT_ROUNDS = 12


def generate_api_key() -> str:
    """Génère une api_key URL-safe de 48 caractères (base64-url sans padding).

    Source : secrets.token_bytes(36) → 36 bytes = 48 chars en base64-url.
    Charset : [A-Za-z0-9_-], suffisamment dense pour un usage en header HTTP.
    """
    raw = secrets.token_bytes(_KEY_BYTES)
    # 36 bytes → 48 chars en base64-url sans padding (déterministe).
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def hash_api_key(key: str) -> str:
    """Calcule le hash bcrypt d'une api_key (rounds=12, ~100ms).

    Lève `ValueError` si la clé est vide ou si elle dépasse 72 bytes UTF-8
    (limite bcrypt 5.x).
    """
    if not key:
        raise ValueError("api_key must not be empty")
    if len(key.encode("utf-8")) > 72:
        raise ValueError("api_key too long (>72 bytes UTF-8)")
    salt = bcrypt.gensalt(rounds=_BCRYPT_ROUNDS)
    return bcrypt.hashpw(key.encode("utf-8"), salt).decode("ascii")


def verify_api_key(provided: str, stored_hash: str) -> bool:
    """Vérifie qu'une api_key correspond au hash stocké.

    Retourne `False` (sans lever) si le hash n'est pas un format bcrypt valide
    — autorise l'usage en routeur sans try/except verbeux.
    bcrypt.checkpw est timing-safe par construction.
    """
    try:
        return bcrypt.checkpw(provided.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        return False
