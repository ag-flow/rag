"""Surface MCP en serveur de ressources OAuth 2.1 (ticket 3d457a26).

Spécification MCP (autorisation) : RFC 9728 (métadonnées de ressource
protégée), RFC 6750 (`WWW-Authenticate: Bearer`), validation d'audience.
Deux porteurs coexistent sur `/mcp`, chacun par un chemin EXPLICITE :
- un JWT de l'IdP (`header.payload.signature`) → ce module ;
- une clé API opaque (48 car. base64url, sans point) → chemin historique du
  dispatcher, inchangé.

Ce module ne connaît que des valeurs spécifiées (issuer, audience, `sub`) :
l'identifiant de ressource est une VALEUR DE CONFIGURATION, jamais dérivée de
la structure realm/client de l'IdP (standard globals OIDC §10.3).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog

from rag.api.errors import OidcInvalidToken, OidcKeycloakUnreachable
from rag.services.oidc import OidcService

log = structlog.get_logger(__name__)

# RFC 9728 §3.1 : pour une ressource `https://h/mcp`, le document vit à
# `https://h/.well-known/oauth-protected-resource/mcp` (insertion de chemin).
METADATA_PATH = "/.well-known/oauth-protected-resource"
RESOURCE_PATH = "/mcp"

# Rôle en base (source de vérité depuis la migration 099) → portée des outils.
# Le modèle de portées n'est pas refait : un jeton reçoit exactement les
# autorisations d'une clé de même portée. `read_write` n'a pas de rôle
# humain correspondant : il reste propre aux clés (indexation par un agent).
ROLE_TO_SCOPE = {"rag-admin": "admin", "rag-viewer": "read"}

# Trois segments base64url : la forme compacte d'un JWS. Une clé API ragflow
# n'a jamais de point — l'aiguillage ne peut pas confondre les deux porteurs.
_JWT_RE = re.compile(r"^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$")

_SELECT_BY_ANCHOR = "SELECT owner_id, role FROM users WHERE oidc_issuer = $1 AND oidc_sub = $2"


class McpTokenRefusedError(Exception):
    """Jeton refusé. `status` 401 (jeton invalide) ou 403 (valide, sans droit) ;
    `error` est un code RFC 6750, `reason` un code stable sans secret."""

    def __init__(self, status: int, error: str, reason: str) -> None:
        super().__init__(reason)
        self.status = status
        self.error = error
        self.reason = reason


@dataclass(frozen=True)
class McpTokenIdentity:
    owner_id: str
    scope: str
    sub: str


def looks_like_jwt(token: str) -> bool:
    return _JWT_RE.match(token) is not None


def resource_uri(public_base: str, configured: str | None) -> str:
    """Identifiant de la ressource : la configuration si posée, sinon `<url publique>/mcp`."""
    return (configured or f"{public_base.rstrip('/')}{RESOURCE_PATH}").rstrip("/")


def metadata_url(public_base: str) -> str:
    return f"{public_base.rstrip('/')}{METADATA_PATH}{RESOURCE_PATH}"


def www_authenticate(public_base: str, *, error: str | None = None) -> str:
    """En-tête d'un 401/403 : désigne les métadonnées, d'où le client découvre
    le serveur d'autorisation. Le code d'erreur seul : jamais de détail
    pouvant recopier une partie du jeton."""
    value = f'Bearer resource_metadata="{metadata_url(public_base)}"'
    if error is not None:
        value += f', error="{error}"'
    return value


def protected_resource_metadata(resource: str, issuer: str) -> dict[str, Any]:
    return {
        "resource": resource,
        "authorization_servers": [issuer],
        "bearer_methods_supported": ["header"],
        "resource_name": "ragflow — recherche sémantique",
    }


async def resolve_token_identity(
    oidc: OidcService, config_pool: asyncpg.Pool, token: str, *, audience: str
) -> McpTokenIdentity:
    """Vérifie le jeton (signature, iss, aud, exp) puis le rattache à un compte.

    Fail closed à chaque étape : pas de config OIDC, IdP muet, jeton invalide,
    compte inconnu ou sans rôle → refus, jamais une portée par défaut.
    """
    config = await oidc.get_config()
    if config is None:
        raise McpTokenRefusedError(401, "invalid_token", "oidc_not_configured")
    try:
        claims = await oidc.verify_access_token(token, config=config, audience=audience)
    except OidcInvalidToken as exc:
        # Le motif d'audience est distingué : c'est le refus d'un jeton
        # légitime destiné à un AUTRE service, à diagnostiquer côté client.
        reason = "audience" if exc.reason == "invalid_claim:aud" else exc.reason
        raise McpTokenRefusedError(401, "invalid_token", reason) from exc
    except OidcKeycloakUnreachable as exc:
        raise McpTokenRefusedError(401, "invalid_token", "idp_unreachable") from exc
    sub = claims.get("sub")
    if not isinstance(sub, str) or not sub:
        raise McpTokenRefusedError(401, "invalid_token", "sub_missing")
    row = await config_pool.fetchrow(_SELECT_BY_ANCHOR, config.issuer, sub)
    # Pas de provisioning ici : un jeton d'accès MCP ne porte pas forcément
    # l'email vérifié qu'exige le pont d'identité (oidc_identity) — créer un
    # compte depuis ce chemin court-circuiterait la liaison. Le compte naît
    # à la première connexion à l'IHM.
    if row is None:
        raise McpTokenRefusedError(403, "insufficient_scope", "user_not_provisioned")
    # Un rôle absent n'est pas un rôle vide : c'est un compte qu'un admin n'a
    # pas encore qualifié — refus, pas une lecture par défaut.
    scope = ROLE_TO_SCOPE.get(row["role"] or "")
    if scope is None:
        raise McpTokenRefusedError(403, "insufficient_scope", "role_unknown")
    return McpTokenIdentity(owner_id=str(row["owner_id"]), scope=scope, sub=sub)
