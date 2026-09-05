from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status

from rag.auth.obo_resolver import resolve_effective_owner_id


@dataclass
class AuthContext:
    workspace_id: UUID
    indexer_used: str
    owner_id: str  # propriétaire de la clé API — sha256(email), scope de sa bibliothèque


@dataclass
class ReadAuthContext:
    """Contexte d'une requête de LECTURE par clé API (scope read ou supérieur).

    Porte de quoi atteindre la base workspace (`rag_cnx`) et la base config
    (`workspace_id`), plus l'owner et le scope de la clé pour l'autorisation fine.
    """

    workspace_id: UUID
    workspace_name: str
    rag_cnx: str
    owner_id: str
    scope: str  # read | read_write | admin


@dataclass
class OwnerAuthContext:
    """Contexte owner-scopé SANS workspace (bibliothèque de stratégies, etc.)."""

    owner_id: str
    scope: str  # read | read_write | admin


def _extract_bearer(request: Request) -> str:
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing_bearer_token",
        )
    parts = auth_header.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_auth_scheme",
        )
    return parts[1].strip()


# Lookup clé utilisateur active de niveau ÉCRITURE (scope read_write | admin).
# Le workspace doit être PARTAGÉ (owner NULL) ou possédé par le propriétaire de
# la clé (migration 068). Le chemin lecture vit dans services/mcp.py et
# api/mcp_standard.py.
_WRITE_LOOKUP_SQL = """
    SELECT w.id,
           ic.provider || '/' || ic.model AS indexer_used,
           k.owner_id
    FROM workspaces w
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    JOIN user_api_keys k ON (w.owner_id IS NULL OR w.owner_id = k.owner_id)
    WHERE w.name = $1
      AND k.fingerprint = $2
      AND k.scope IN ('read_write', 'admin')
      AND k.revoked_at IS NULL
      AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
"""


async def require_workspace_apikey(
    name: str,
    request: Request,
) -> AuthContext:
    """Dep FastAPI : valide `Authorization: Bearer <api_key>` pour l'ÉCRITURE.

    Clés utilisateur (user_api_keys) : la valeur n'est jamais stockée, seule
    l'empreinte SHA-256 l'est. La clé doit être de niveau `read_write` ou
    `admin` (indexation push / suppression), appliqué à tous les workspaces.

    - 401 uniforme si Bearer absent / scheme invalide / clé invalide /
      workspace inconnu / permission manquante.
    """
    api_key = _extract_bearer(request)
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()

    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(_WRITE_LOOKUP_SQL, name, fingerprint)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )
    return AuthContext(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        owner_id=row["owner_id"],
    )


# Lookup clé utilisateur active de niveau LECTURE (scope read | read_write |
# admin). Même règle de visibilité workspace que l'écriture (partagé ou possédé),
# mais autorise le scope `read`. `rag_cnx` sert à atteindre la base workspace.
_READ_LOOKUP_SQL = """
    SELECT w.id, w.name, w.rag_cnx, k.owner_id, k.scope
    FROM user_api_keys k
    JOIN workspaces w ON (w.owner_id IS NULL OR w.owner_id = k.owner_id)
    WHERE w.name = $1
      AND k.fingerprint = $2
      AND k.scope IN ('read', 'read_write', 'admin')
      AND k.revoked_at IS NULL
      AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
"""

_OWNER_LOOKUP_SQL = """
    SELECT owner_id, scope
    FROM user_api_keys
    WHERE fingerprint = $1
      AND scope IN ('read', 'read_write', 'admin')
      AND revoked_at IS NULL
      AND (rotated_at IS NULL OR rotated_at > now() - interval '72 hours')
"""


async def require_workspace_apikey_read(
    name: str,
    request: Request,
) -> ReadAuthContext:
    """Dep FastAPI : valide `Authorization: Bearer <api_key>` pour la LECTURE.

    Autorise les clés de niveau `read`, `read_write` ou `admin`. Le workspace
    doit être partagé (owner NULL) ou possédé par le propriétaire de la clé —
    sinon 401 uniforme (indistinction inconnu/interdit).
    """
    api_key = _extract_bearer(request)
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()

    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(_READ_LOOKUP_SQL, name, fingerprint)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )
    return ReadAuthContext(
        workspace_id=row["id"],
        workspace_name=row["name"],
        rag_cnx=row["rag_cnx"],
        owner_id=row["owner_id"],
        scope=row["scope"],
    )


# Résolution d'un workspace ciblé PAR SON SLUG (dans le corps/query), une fois
# l'owner+scope de la clé connus. Remplace le couplage workspace-dans-l'URL :
# le workspace est un paramètre d'appel, comme pour les outils MCP.
_WRITE_WS_SQL = """
    SELECT w.id, ic.provider || '/' || ic.model AS indexer_used
    FROM workspaces w
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    WHERE w.name = $1 AND (w.owner_id IS NULL OR w.owner_id = $2)
"""

_READ_WS_SQL = """
    SELECT w.id, w.name, w.rag_cnx
    FROM workspaces w
    WHERE w.name = $1 AND (w.owner_id IS NULL OR w.owner_id = $2)
"""


async def resolve_apikey_write_workspace(
    request: Request, *, owner_id: str, scope: str, workspace: str
) -> AuthContext:
    """Résout un workspace pour une ÉCRITURE par clé API (workspace en paramètre).

    Exige un scope `read_write`/`admin` et un workspace visible (partagé ou
    possédé). 401 uniforme sinon (indistinction clé/scope/workspace)."""
    if scope not in ("read_write", "admin"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_workspace_apikey")
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(_WRITE_WS_SQL, workspace, owner_id)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_workspace_apikey")
    return AuthContext(
        workspace_id=row["id"], indexer_used=row["indexer_used"], owner_id=owner_id
    )


async def resolve_apikey_read_workspace(
    request: Request, *, owner_id: str, scope: str, workspace: str
) -> ReadAuthContext:
    """Résout un workspace pour une LECTURE par clé API (workspace en query).

    Scope `read`+ suffit. 401 uniforme si workspace non visible."""
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(_READ_WS_SQL, workspace, owner_id)
    if row is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid_workspace_apikey")
    return ReadAuthContext(
        workspace_id=row["id"],
        workspace_name=row["name"],
        rag_cnx=row["rag_cnx"],
        owner_id=owner_id,
        scope=scope,
    )


async def require_apikey_owner(request: Request) -> OwnerAuthContext:
    """Dep FastAPI : identifie l'owner + scope d'une clé API, SANS workspace.

    Pour les ressources owner-scopées non liées à un workspace (bibliothèque de
    stratégies de chunking) et pour l'ingestion `/api/v1/index`, où le workspace
    est un paramètre d'appel. 401 uniforme si la clé est absente/invalide.

    L'owner retenu passe par `resolve_effective_owner_id` — même point
    d'application de l'OBO que le middleware MCP, pour que les deux surfaces
    attribuent le MÊME `owner_id` à un humain donné. La clé est validée AVANT :
    une identité signée ne rattrape jamais une clé invalide.
    """
    api_key = _extract_bearer(request)
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()

    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(_OWNER_LOOKUP_SQL, fingerprint)
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_apikey",
        )
    owner_id = await resolve_effective_owner_id(
        pool,
        list(request.headers.raw),
        api_key,
        key_owner_id=row["owner_id"],
        surface="rest",
    )
    return OwnerAuthContext(owner_id=owner_id, scope=row["scope"])
