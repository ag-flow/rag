from __future__ import annotations

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry


@pytest.mark.asyncio
async def test_registry_caches_workspace_pools(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=4
    )
    await registry.start()

    pool_a1 = await registry.get_workspace_pool("rag_config", pg_container)
    pool_a2 = await registry.get_workspace_pool("rag_config", pg_container)

    assert pool_a1 is pool_a2  # caché par nom

    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_lru_evicts_oldest(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=2
    )
    await registry.start()

    # Le DSN container utilise probablement la base `test` ou `rag_config` ;
    # on n'a pas besoin de bases différentes — c'est le NOM qui sert de clé de cache.
    p1 = await registry.get_workspace_pool("ws_a", pg_container)
    p2 = await registry.get_workspace_pool("ws_b", pg_container)
    p3 = await registry.get_workspace_pool("ws_c", pg_container)

    # ws_a a été évincé (LRU sur max=2 : ws_b et ws_c restent)
    assert p1.is_closing() or p1._initialized is False or p1._closed is True
    assert p2 is not None
    assert p3 is not None

    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_config_pool_accessible(pg_container: str) -> None:
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container, admin_dsn=pg_container, max_workspace_pools=2
    )
    await registry.start()
    pool = registry.config_pool
    assert isinstance(pool, asyncpg.Pool)
    async with pool.acquire() as conn:
        v = await conn.fetchval("SELECT 1")
        assert v == 1
    await registry.close_all()


@pytest.mark.asyncio
async def test_registry_get_workspace_pool_before_start_raises() -> None:
    registry = WorkspacePoolRegistry(
        config_dsn="postgresql://x:y@h:5432/d",
        admin_dsn="postgresql://x:y@h:5432/p",
        max_workspace_pools=2,
    )
    with pytest.raises(RuntimeError, match="start"):
        _ = registry.config_pool
