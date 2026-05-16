from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import asyncpg
import httpx
import structlog

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


@dataclass(frozen=True)
class OidcConfig:
    """Config OIDC stockée en `oidc_config` (1 row max)."""

    issuer: str
    client_id: str
    client_secret_ref: str  # clé logique Harpocrate


class OidcService:
    """Encapsule tout l'état OIDC : config DB, discovery + JWKS cache,
    code exchange, JWT verify, refresh, logout URL.

    Thread-safety : asyncio single-thread - pas de lock requis.
    """

    _DISCOVERY_TTL_SECONDS = 3600

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        secret_resolver: _ResolverProtocol,
        public_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config_pool = config_pool
        self._secret_resolver = secret_resolver
        self._public_url = public_url.rstrip("/")
        self._http_client = http_client  # injection pour tests

    # --- CRUD config ---

    async def get_config(self) -> OidcConfig | None:
        row = await self._config_pool.fetchrow(
            "SELECT issuer, client_id, client_secret_ref FROM oidc_config LIMIT 1"
        )
        if row is None:
            return None
        return OidcConfig(
            issuer=row["issuer"],
            client_id=row["client_id"],
            client_secret_ref=row["client_secret_ref"],
        )

    async def upsert_config(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret_ref: str,
    ) -> OidcConfig:
        """Remplace toute config existante. Pattern : 1 row max en table.

        DELETE + INSERT en transaction. On garantit qu'il y a au plus 1 row
        à tout moment (pas de PK naturel, contrainte applicative).
        """
        async with self._config_pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM oidc_config")
            await conn.execute(
                """
                INSERT INTO oidc_config (issuer, client_id, client_secret_ref)
                VALUES ($1, $2, $3)
                """,
                issuer,
                client_id,
                client_secret_ref,
            )
        log.info("oidc.config.upserted", issuer=issuer, client_id=client_id)
        return OidcConfig(
            issuer=issuer,
            client_id=client_id,
            client_secret_ref=client_secret_ref,
        )
