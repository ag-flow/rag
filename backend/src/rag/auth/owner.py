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


def get_current_principal_email(request: Request) -> str | None:
    """Email du principal de session — PIVOT unique d'identité (table users).

    - Session locale : email du payload de session.
    - Session OIDC : claim `email` (repli `preferred_username` si le token n'en
      porte pas — IdP mal configuré, on ne casse pas la session).
    - Master key / aucune session : None (pas d'humain identifiable).
    """
    if request.headers.get("Authorization"):
        return None

    local_session = request.session.get("_local_session")
    if local_session:
        return local_session.get("email", _SYSTEM_OWNER_EMAIL)

    oidc_session = request.session.get("_oidc_session")
    if oidc_session:
        id_token = oidc_session.get("id_token", "")
        claims = _decode_jwt_payload(id_token)
        return claims.get("email") or claims.get("preferred_username", "")

    return None


def get_current_owner_id(request: Request) -> str:
    """Résout le owner_id de la requête courante.

    owner_id = sha256(email) — l'EMAIL du user (table users) est le pivot
    d'identité unique : session OIDC (claim email), session locale (email),
    et OBO (GUID → users.identity → users.email) donnent le MÊME owner_id.
    Master key / aucune session → owner système constant.
    """
    email = get_current_principal_email(request)
    if email is None:
        return principal_to_owner_id(_SYSTEM_OWNER_EMAIL)
    return principal_to_owner_id(email)
