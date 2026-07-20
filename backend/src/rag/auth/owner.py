from __future__ import annotations

import base64
import hashlib
import json

from fastapi import Request

_SYSTEM_OWNER_EMAIL = "system@rag.local"


def principal_to_owner_id(principal: str) -> str:
    """owner_id = sha256(principal.lower()).

    Le `principal` est le login humain reconnu de bout en bout : `owner_login`
    du portail (propagé signé par OBO) = `preferred_username` OIDC. Même clé
    partout, pour que l'attribution OBO et la session d'un même humain donnent
    le MÊME owner_id."""
    return hashlib.sha256(principal.lower().encode()).hexdigest()


# Alias historique (mêmes octets) : le principal peut être un email de session
# locale/break-glass comme un login OIDC — la dérivation est identique.
email_to_owner_id = principal_to_owner_id


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
    2. Session locale → email du payload de session (break-glass, hors portail)
    3. Session OIDC → `preferred_username` (= owner_login portail, clé OBO)

    Le principal OIDC est le MÊME login que celui propagé par OBO : attribution
    par session et attribution par OBO produisent un owner_id identique.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header:
        return principal_to_owner_id(_SYSTEM_OWNER_EMAIL)

    local_session = request.session.get("_local_session")
    if local_session:
        email = local_session.get("email", _SYSTEM_OWNER_EMAIL)
        return principal_to_owner_id(email)

    oidc_session = request.session.get("_oidc_session")
    if oidc_session:
        id_token = oidc_session.get("id_token", "")
        claims = _decode_jwt_payload(id_token)
        # preferred_username = owner_login portail (clé OBO) ; email en repli.
        principal = claims.get("preferred_username") or claims.get("email", "")
        return principal_to_owner_id(principal)

    return principal_to_owner_id(_SYSTEM_OWNER_EMAIL)
