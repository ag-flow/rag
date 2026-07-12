from __future__ import annotations

import asyncio
from collections import OrderedDict

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class WorkspacePoolRegistry:
    """Registry centralisé des pools asyncpg.

    - `config_pool` : pool unique vers la base `rag_config` (toujours actif).
    - `admin_pool` : pool vers la base système `postgres` (utilisé pour CREATE DATABASE).
    - Pools workspaces : créés à la volée, cachés en LRU avec `max_workspace_pools`.
    """

    def __init__(
        self,
        *,
        config_dsn: str,
        admin_dsn: str,
        max_workspace_pools: int = 16,
        min_size: int = 1,
        max_size: int = 5,
    ) -> None:
        self._config_dsn = config_dsn
        self._admin_dsn = admin_dsn
        self._max_workspace_pools = max_workspace_pools
        self._min_size = min_size
        self._max_size = max_size

        self._config_pool: asyncpg.Pool | None = None
        self._admin_pool: asyncpg.Pool | None = None
        self._workspace_pools: OrderedDict[str, asyncpg.Pool] = OrderedDict()
        # Sérialise le get-or-create et l'éviction pour éviter la création de
        # pools dupliqués sous accès concurrent (BUG-058a).
        self._workspace_lock = asyncio.Lock()

    async def start(self) -> None:
        """Initialise les pools `config` et `admin`. Idempotent."""
        if self._config_pool is None:
            self._config_pool = await asyncpg.create_pool(
                self._config_dsn, min_size=self._min_size, max_size=self._max_size
            )
            log.info("pool.config.opened")
        if self._admin_pool is None:
            self._admin_pool = await asyncpg.create_pool(self._admin_dsn, min_size=1, max_size=2)

    @property
    def config_pool(self) -> asyncpg.Pool:
        if self._config_pool is None:
            raise RuntimeError("WorkspacePoolRegistry.start() not called")
        return self._config_pool

    @property
    def admin_pool(self) -> asyncpg.Pool:
        if self._admin_pool is None:
            raise RuntimeError("WorkspacePoolRegistry.start() not called")
        return self._admin_pool

    async def get_workspace_pool(self, workspace_name: str, dsn: str) -> asyncpg.Pool:
        """Retourne (et crée si besoin) un pool pour la base d'un workspace.

        Cache LRU : si on dépasse `max_workspace_pools`, le moins récemment
        utilisé est fermé.

        Le get-or-create et l'éviction sont sérialisés par un verrou pour
        empêcher deux appels concurrents de créer chacun un pool (fuite de
        connexions, BUG-058a).
        """
        async with self._workspace_lock:
            existing = self._workspace_pools.get(workspace_name)
            if existing is not None:
                self._workspace_pools.move_to_end(workspace_name)
                return existing

            pool = await asyncpg.create_pool(
                dsn, min_size=self._min_size, max_size=self._max_size
            )
            self._workspace_pools[workspace_name] = pool
            log.info("pool.workspace.opened", workspace=workspace_name)

            await self._evict_lru()
            return pool

    async def _evict_lru(self) -> None:
        """Ferme les pools au-delà de la capacité, du moins récent au plus
        récent, mais seulement ceux sans connexion active pour ne jamais
        fermer un pool servant une requête vivante (BUG-058b).

        À appeler en tenant `self._workspace_lock`.
        """
        for name in list(self._workspace_pools.keys()):
            if len(self._workspace_pools) <= self._max_workspace_pools:
                break
            pool = self._workspace_pools[name]
            if pool.get_size() - pool.get_idle_size() > 0:
                continue  # connexions en cours d'utilisation : on ne ferme pas
            del self._workspace_pools[name]
            await pool.close()
            log.info("pool.workspace.evicted", workspace=name)

    async def close_all(self) -> None:
        async with self._workspace_lock:
            for _name, pool in list(self._workspace_pools.items()):
                await pool.close()
            self._workspace_pools.clear()

        if self._config_pool is not None:
            await self._config_pool.close()
            self._config_pool = None
        if self._admin_pool is not None:
            await self._admin_pool.close()
            self._admin_pool = None
