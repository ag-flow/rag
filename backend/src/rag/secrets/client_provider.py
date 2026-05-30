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
        self._clients_by_name: dict[str, HarpocrateVaultClient] = {}
        self._default_name: str | None = None
        self._loaded_at: float = 0.0
        self._invalidated: bool = True
        self._lock = asyncio.Lock()

    def invalidate(self) -> None:
        self._invalidated = True

    async def get_client(self, vault_name: str) -> HarpocrateVaultClient:
        """Retourne le client pour `vault_name`.

        Essaie d'abord par api_key_id (ancien format des refs), puis par
        nom du coffre (nouveau format des harpo_path issus de provider_api_keys,
        git_credentials, ssh_keys).
        """
        await self._ensure_loaded()
        client = self._clients.get(vault_name) or self._clients_by_name.get(vault_name)
        if client is None:
            raise VaultNotFoundError(vault_name)
        return client

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
            clients_by_name: dict[str, HarpocrateVaultClient] = {}
            for v in vaults:
                api_key = await self._service.reveal_api_key(conn, v.id)
                if api_key is None:
                    continue
                client = HarpocrateVaultClient(url=v.base_url, token=api_key)
                # Index par api_key_id (ancien format des refs workspace)
                clients[v.api_key_id] = client
                # Index par vault_name (nouveau format des harpo_path de provider_api_keys,
                # git_credentials, ssh_keys : ${vault://<vault_name>:<path>})
                clients_by_name[v.name] = client
        self._clients = clients
        self._clients_by_name = clients_by_name
        self._default_name = next(
            (v.api_key_id for v in vaults if v.is_default),
            None,
        )
        if self._default_name is None:
            log.warning(
                "vault.default_missing",
                clients_count=len(clients),
            )
