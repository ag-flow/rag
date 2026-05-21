from __future__ import annotations

import asyncio
import time
from typing import TYPE_CHECKING

import structlog
from asyncpg import Pool

from rag.secrets.exceptions import VaultNotFoundError
from rag.secrets.vault import HarpocrateVaultClient

if TYPE_CHECKING:
    from rag.config import Settings
    from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)

_TTL_SECONDS = 60


class HarpocrateClientProvider:
    """Cache et fournit des `HarpocrateVaultClient` par nom de coffre.

    Source unique : `HarpocrateVaultsService.list_all` (table harpocrate_vaults).
    TTL mémoire de 60 secondes + `invalidate()` manuel pour forcer un rechargement
    immédiat. Si la table est vide, aucun client n'est disponible.
    """

    def __init__(
        self,
        settings: Settings,  # conservé pour compatibilité des call-sites ; non utilisé
        vaults_service: HarpocrateVaultsService,
        db_pool: Pool,
    ) -> None:
        self._service = vaults_service
        self._pool = db_pool
        self._clients: dict[str, HarpocrateVaultClient] = {}
        self._default_name: str | None = None
        self._loaded_at: float = 0.0
        self._invalidated: bool = True
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._invalidated = True

    async def get_client(self, vault_name: str) -> HarpocrateVaultClient:
        await self._ensure_loaded()
        try:
            return self._clients[vault_name]
        except KeyError as exc:
            raise VaultNotFoundError(vault_name) from exc

    async def get_default_vault_name(self) -> str | None:
        await self._ensure_loaded()
        return self._default_name

    async def _ensure_loaded(self) -> None:
        if not self._invalidated and time.monotonic() - self._loaded_at < _TTL_SECONDS:
            return
        async with self._lock:
            if not self._invalidated and time.monotonic() - self._loaded_at < _TTL_SECONDS:
                return
            await self._load()
            self._loaded_at = time.monotonic()
            self._invalidated = False

    async def _load(self) -> None:
        async with self._pool.acquire() as conn:
            vaults = await self._service.list_all(conn)

        if not vaults:
            self._clients = {}
            self._default_name = None
            log.info("vault.load.empty", reason="table harpocrate_vaults vide")
            return

        async with self._pool.acquire() as conn:
            clients: dict[str, HarpocrateVaultClient] = {}
            for v in vaults:
                api_key = await self._service.reveal_api_key(conn, v.id)
                if api_key is None:
                    continue
                clients[v.name] = HarpocrateVaultClient(
                    url=v.base_url,
                    token=api_key,
                )
        self._clients = clients
        self._default_name = next(
            (v.name for v in vaults if v.is_default),
            None,
        )
        if self._default_name is None:
            log.warning(
                "vault.default_missing",
                clients_count=len(clients),
            )
