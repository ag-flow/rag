from __future__ import annotations

import base64
import hashlib
import json

from fastapi import Request


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
    1. Bearer token → master key → email bootstrap admin
    2. Session locale → email bootstrap admin
    3. Session OIDC → email depuis JWT payload
    """
    settings = request.app.state.settings

    auth_header = request.headers.get("Authorization")
    if auth_header:
        return email_to_owner_id(settings.rag_bootstrap_admin_email)

    local_session = request.session.get("_local_session")
    if local_session:
        return email_to_owner_id(settings.rag_bootstrap_admin_email)

    oidc_session = request.session.get("_oidc_session")
    if oidc_session:
        id_token = oidc_session.get("id_token", "")
        claims = _decode_jwt_payload(id_token)
        email = claims.get("email", "")
        return email_to_owner_id(email)

    return email_to_owner_id(settings.rag_bootstrap_admin_email)
