from __future__ import annotations

import base64
import hashlib
import json

from fastapi import Request

_SYSTEM_OWNER_EMAIL = "system@rag.local"


def email_to_owner_id(email: str) -> str:
    """Retourne sha256(email.lower()) comme identifiant owner."""
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _decode_jwt_payload(token: str) -> dict:
    """Décode le payload d'un JWT sans vérification de signature."""
    payload_b64 = token.split(".")[1]
    padding = -len(payload_b64) % 4
    if padding:
        payload_b64 += "=" * padding
    return json.loads(base64.urlsafe_b64decode(payload_b64))


def get_current_owner_id(request: Request) -> str:
    """Résout le owner_id de la requête courante.

    Priorité :
    1. Bearer token (master key) → owner système constant
    2. Session locale → email depuis le payload de session
    3. Session OIDC → email depuis JWT payload
    """
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return email_to_owner_id(_SYSTEM_OWNER_EMAIL)

    local_session = request.session.get("_local_session")
    if local_session:
        email = local_session.get("email", _SYSTEM_OWNER_EMAIL)
        return email_to_owner_id(email)

    oidc_session = request.session.get("_oidc_session")
    if oidc_session:
        id_token = oidc_session.get("id_token", "")
        claims = _decode_jwt_payload(id_token)
        email = claims.get("email", "")
        return email_to_owner_id(email)

    return email_to_owner_id(_SYSTEM_OWNER_EMAIL)
