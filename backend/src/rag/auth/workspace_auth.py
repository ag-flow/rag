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


# Lookup clé utilisateur active avec grant d'ÉCRITURE sur le workspace.
# Requête entièrement littérale (le chemin lecture vit dans services/mcp.py
# et api/mcp_standard.py avec g.can_read).
_WRITE_LOOKUP_SQL = """
    SELECT w.id,
           ic.provider || '/' || ic.model AS indexer_used
    FROM workspaces w
    JOIN user_api_key_workspaces g ON g.workspace_id = w.id
    JOIN user_api_keys k ON k.id = g.api_key_id
    JOIN indexer_configs ic ON ic.workspace_id = w.id
    WHERE w.name = $1
      AND k.fingerprint = $2
      AND g.can_write
      AND k.revoked_at IS NULL
      AND (k.rotated_at IS NULL OR k.rotated_at > now() - interval '72 hours')
"""


async def require_workspace_apikey(
    name: str,
    request: Request,
) -> AuthContext:
    """Dep FastAPI : valide `Authorization: Bearer <api_key>` pour l'ÉCRITURE.

    Clés utilisateur (user_api_keys) : la valeur n'est jamais stockée, seule
    l'empreinte SHA-256 l'est. Le grant du workspace doit porter `can_write`
    (indexation push / suppression).

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
    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
