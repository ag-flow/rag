from __future__ import annotations

import time
from collections import OrderedDict
from dataclasses import dataclass
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status

from rag.api.errors import WorkspaceNotFound
from rag.services.apikey import verify_api_key


@dataclass
class _CacheEntry:
    workspace_id: UUID
    indexer_used: str
    inserted_at: float


class ApiKeyCache:
    """Cache LRU+TTL des api_keys workspace validées par bcrypt.

    Clé : (workspace_name, api_key_clair). Valeur : _CacheEntry.

    Le cache ne contient que des entrées dont la vérification bcrypt a réussi.
    Un attaquant qui présente une clé invalide paie bcrypt à chaque tentative,
    sans pollution du cache (LRU évincte tout de toute façon).
    """

    def __init__(self, *, max_size: int = 256, ttl_seconds: int = 300) -> None:
        self._max_size = max_size
        self._ttl_seconds = ttl_seconds
        self._store: OrderedDict[tuple[str, str], _CacheEntry] = OrderedDict()

    def get(self, workspace_name: str, api_key: str) -> _CacheEntry | None:
        key = (workspace_name, api_key)
        entry = self._store.get(key)
        if entry is None:
            return None
        if time.monotonic() - entry.inserted_at > self._ttl_seconds:
            del self._store[key]
            return None
        self._store.move_to_end(key)
        return entry

    def put(self, workspace_name: str, api_key: str, entry: _CacheEntry) -> None:
        key = (workspace_name, api_key)
        self._store[key] = entry
        self._store.move_to_end(key)
        while len(self._store) > self._max_size:
            self._store.popitem(last=False)

    def invalidate(self, workspace_name: str) -> None:
        to_delete = [k for k in self._store if k[0] == workspace_name]
        for k in to_delete:
            del self._store[k]


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


async def require_workspace_apikey(
    name: str,
    request: Request,
) -> AuthContext:
    """Dependency FastAPI : valide `Authorization: Bearer <WORKSPACE_API_KEY>`
    contre `workspaces[name].api_key_hash` (bcrypt), avec cache LRU+TTL.

    - 401 si bearer absent / mauvais scheme / clé invalide.
    - 404 si workspace inexistant ou pas d'indexer_config.
    - Sur succès : retourne `AuthContext(workspace_id, indexer_used)`.
    """
    api_key = _extract_bearer(request)

    cache: ApiKeyCache = request.app.state.apikey_cache
    pool: asyncpg.Pool = request.app.state.pools.config_pool

    entry = cache.get(name, api_key)
    if entry is not None:
        return AuthContext(workspace_id=entry.workspace_id, indexer_used=entry.indexer_used)

    row = await pool.fetchrow(
        """
        SELECT w.id, w.api_key_hash,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1
        """,
        name,
    )
    if row is None:
        raise WorkspaceNotFound(name)

    if not verify_api_key(api_key, row["api_key_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    new_entry = _CacheEntry(
        workspace_id=row["id"],
        indexer_used=row["indexer_used"],
        inserted_at=time.monotonic(),
    )
    cache.put(name, api_key, new_entry)
    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
