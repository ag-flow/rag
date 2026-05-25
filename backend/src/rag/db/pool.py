from __future__ import annotations

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
        """
        if workspace_name in self._workspace_pools:
            self._workspace_pools.move_to_end(workspace_name)
            return self._workspace_pools[workspace_name]

        pool = await asyncpg.create_pool(dsn, min_size=self._min_size, max_size=self._max_size)
        self._workspace_pools[workspace_name] = pool
        log.info("pool.workspace.opened", workspace=workspace_name)

        # Eviction LRU
        while len(self._workspace_pools) > self._max_workspace_pools:
            oldest_name, oldest_pool = self._workspace_pools.popitem(last=False)
            await oldest_pool.close()
            log.info("pool.workspace.evicted", workspace=oldest_name)

        return pool

    async def close_all(self) -> None:
        for _name, pool in list(self._workspace_pools.items()):
            await pool.close()
        self._workspace_pools.clear()

        if self._config_pool is not None:
            await self._config_pool.close()
            self._config_pool = None
        if self._admin_pool is not None:
            await self._admin_pool.close()
            self._admin_pool = None
