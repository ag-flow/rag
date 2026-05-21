from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from secrets import compare_digest
from uuid import UUID

import asyncpg
from fastapi import HTTPException, Request, status


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
    """Dependency FastAPI : valide `Authorization: Bearer <WORKSPACE_API_KEY>`.

    Lookup O(1) par fingerprint SHA-256 puis comparaison timing-safe sur
    la valeur déchiffrée (pgp_sym_decrypt). Cache LRU+TTL conservé.

    - 401 si bearer absent / mauvais scheme / clé invalide.
    - 401 si workspace inexistant (401 uniforme — ne révèle pas l'existence).
    - 503 si DEK absent en config.
    - Sur succès : retourne `AuthContext(workspace_id, indexer_used)`.
    """
    api_key = _extract_bearer(request)

    pool: asyncpg.Pool = request.app.state.pools.config_pool
    dek: str | None = request.app.state.settings.api_key_dek
    if dek is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="api_key_dek_unavailable",
        )

    # NOTE(T6): require_workspace_apikey sera migré vers Harpocrate en T6.
    # Temporairement, le cache n'est pas utilisé ici — lookup DB direct.
    fingerprint = sha256(api_key.encode("utf-8")).hexdigest()
    row = await pool.fetchrow(
        """
        SELECT w.id,
               pgp_sym_decrypt(w.api_key_encrypted, $2::text)::text AS stored,
               ic.provider || '/' || ic.model AS indexer_used
        FROM workspaces w
        JOIN indexer_configs ic ON ic.workspace_id = w.id
        WHERE w.name = $1 AND w.api_key_fingerprint = $3
        """,
        name,
        dek,
        fingerprint,
    )
    if row is None:
        # Soit le workspace n'existe pas, soit la clé ne correspond pas —
        # 401 dans les deux cas pour ne pas révéler l'existence du workspace.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    # Vérification timing-safe contre collision SHA-256 théorique.
    if not compare_digest(api_key, row["stored"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid_workspace_apikey",
        )

    return AuthContext(workspace_id=row["id"], indexer_used=row["indexer_used"])
