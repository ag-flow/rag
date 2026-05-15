from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

import asyncpg
from fastapi import HTTPException, status

from rag.api.errors import WorkspaceNotFound
from rag.auth.workspace_auth import ApiKeyCache, _CacheEntry
from rag.schemas.mcp import MultiWorkspaceRequest, SingleWorkspaceRequest
from rag.services.apikey import verify_api_key


@dataclass(frozen=True)
class McpWorkspaceRef:
    """Représentation interne d'un workspace+api_key à interroger.

    `frozen=True` : empêche `_search_one` ou `_authenticate` de muter
    accidentellement la ref entre tâches asyncio.gather concurrentes.
    """

    name: str
    api_key: str


def normalize_refs(
    req: SingleWorkspaceRequest | MultiWorkspaceRequest,
) -> list[McpWorkspaceRef]:
    """Convertit le DTO d'entrée en liste interne (ordre préservé)."""
    if isinstance(req, SingleWorkspaceRequest):
        return [McpWorkspaceRef(name=req.workspace, api_key=req.api_key)]
    return [McpWorkspaceRef(name=w.name, api_key=w.api_key) for w in req.workspaces]


async def _authenticate(
    *,
    ref: McpWorkspaceRef,
    config_pool: asyncpg.Pool,
    apikey_cache: ApiKeyCache,
) -> _CacheEntry:
    """Valide la paire (workspace_name, api_key) avec cache LRU+TTL.

    Retourne un `_CacheEntry` (workspace_id, indexer_used, inserted_at).
    - WorkspaceNotFound si workspace inconnu ou pas d'indexer_config.
    - HTTPException 401 si bcrypt verify échoue (clé invalide non mise en cache).
    """
    cached = apikey_cache.get(ref.name, ref.api_key)
    if cached is not None:
        return cached

    row = await config_pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        ref.name,
    )
    if row is None:
        raise WorkspaceNotFound(ref.name)

    if not verify_api_key(ref.api_key, row["api_key_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    apikey_cache.put(ref.name, ref.api_key, entry)
    return entry


async def _load_workspace_context(
    config_pool: asyncpg.Pool,
    name: str,
) -> dict[str, Any]:
    """Charge provider+model+api_key_ref+base_url+rag_cnx pour un workspace.

    Lève RuntimeError si workspace inexistant — `_authenticate` est censé
    avoir validé l'existence avant cet appel ; un None ici trahit une
    corruption d'état entre les deux SELECT.
    """
    row = await config_pool.fetchrow(
        """
        SELECT
            w.name AS workspace_name,
            w.rag_cnx AS rag_cnx,
            ic.provider AS provider,
            ic.model AS model,
            ic.api_key_ref AS api_key_ref,
            ic.base_url AS base_url
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise RuntimeError(f"workspace {name!r} disappeared between auth and load")
    return dict(row)
