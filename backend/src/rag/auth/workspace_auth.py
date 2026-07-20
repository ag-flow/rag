from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status


@dataclass
class AuthContext:
    workspace_id: UUID
    indexer_used: str
    owner_id: str  # propriétaire de la clé API — sha256(email), scope de sa bibliothèque


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
