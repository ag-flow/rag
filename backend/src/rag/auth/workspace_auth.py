from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status

from rag.api.errors import HarpocrateUnreachableForApikey, VaultUnreachable


class ApiKeyCache:
    """Cache process-lifetime des api_keys MCP workspace résolues depuis Harpocrate.

    Clé : `api_key_ref` (string `${vault://<vault>:<path>}`).
    Valeur : api_key en clair.

    Pas de TTL : la valeur survit tant que le process tourne. Invalidation
    explicite via `invalidate(ref)` à la rotation. Cold au démarrage : aucune
    entrée préchargée.
    """

    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    def get(self, ref: str) -> str | None:
        return self._store.get(ref)

    def put(self, ref: str, value: str) -> None:
        self._store[ref] = value

    def invalidate(self, ref: str) -> None:
        self._store.pop(ref, None)


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
    """Dep FastAPI : valide `Authorization: Bearer <api_key>` workspace.

    Lookup O(1) par fingerprint SHA-256 → résolution via cache process-lifetime
    (puis Harpocrate sur miss) → comparaison timing-safe.

    - 401 si Bearer absent / scheme invalide / clé invalide / workspace inconnu.
    - 503 `harpocrate_unreachable` si Harpocrate down sur cache miss.
    """
    api_key = _extract_bearer(request)
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()

    pool: asyncpg.Pool = request.app.state.pools.config_pool
    row = await pool.fetchrow(
        """
        SELECT w.id,
               w.api_key_ref,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1 AND w.api_key_fingerprint = $2
        """,
        name,
        fingerprint,
    )
    if row is None:
        # Workspace inconnu OU bearer ne match aucun fingerprint : 401 uniform.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    cache: ApiKeyCache = request.app.state.apikey_cache
    api_key_ref: str = row["api_key_ref"]
    cached = cache.get(api_key_ref)
    if cached is None:
        resolver = request.app.state.resolver
        try:
            cached = await resolver.resolve_with_retry(api_key_ref)
        except VaultUnreachable as e:
            raise HarpocrateUnreachableForApikey() from e
        cache.put(api_key_ref, cached)

    if not compare_digest(cached, api_key):
        # Très rare : fingerprint matché mais clair non. Possible après
        # rotation Harpocrate hors-bande sans mise à jour fingerprint DB.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
