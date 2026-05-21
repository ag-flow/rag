from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.workspaces import create_workspace, delete_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    async def resolve_with_retry(self, ref: str) -> str:
        assert re.fullmatch(r"\$\{vault://[^:]+:[^}]+\}", ref)
        return "sk-x"


def _make_harpo_service() -> MagicMock:
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    service.get_by_name = AsyncMock(return_value=vault)
    service.write_secret = AsyncMock(return_value=None)
    service.delete_secret = AsyncMock(return_value=None)
    return service


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    yield
    import asyncio

    async def _cleanup() -> None:
        admin = await asyncpg.connect(pg_container.rsplit("/", 1)[0] + "/postgres")
        try:
            for r in await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            ):
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.mark.asyncio
async def test_delete_workspace_drops_db_and_config(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_del",
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )

    await delete_workspace(name="ws_del", config_pool=session_pool, admin_dsn=admin_dsn)

    row = await session_pool.fetchrow("SELECT id FROM workspaces WHERE name=$1", "ws_del")
    assert row is None

    admin = await asyncpg.connect(admin_dsn)
    try:
        present = await admin.fetchval("SELECT 1 FROM pg_database WHERE datname='rag_ws_del'")
    finally:
        await admin.close()
    assert present is None


@pytest.mark.asyncio
async def test_delete_workspace_not_found_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = "postgresql://x:y@z:5432/postgres"
    with pytest.raises(WorkspaceNotFound):
        await delete_workspace(name="absent", config_pool=session_pool, admin_dsn=admin_dsn)


@pytest.mark.asyncio
async def test_delete_workspace_idempotent_retry_after_partial_failure(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """Simule un état orphelin (base physique droppée mais workspace toujours en config)
    et vérifie que le DELETE finit le nettoyage."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_orphan",
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )

    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute('DROP DATABASE IF EXISTS "rag_ws_orphan" WITH (FORCE)')
    finally:
        await admin.close()

    await delete_workspace(name="ws_orphan", config_pool=session_pool, admin_dsn=admin_dsn)

    row = await session_pool.fetchrow("SELECT id FROM workspaces WHERE name=$1", "ws_orphan")
    assert row is None
