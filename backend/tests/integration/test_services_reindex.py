from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import IndexerChangeRequiresReindex, WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.db.workspace_schema import derive_workspace_dsn
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.jobs import reindex_workspace
from rag.services.workspaces import create_workspace

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


async def _create_with_doc(pg_container: str, session_pool: asyncpg.Pool, name: str) -> str:
    """Crée un workspace et insère 1 indexed_document pour simuler du contenu existant."""
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    await create_workspace(
        request=WorkspaceCreateRequest(
            name=name,
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )
    ws_id = await session_pool.fetchval("SELECT id FROM workspaces WHERE name=$1", name)
    await session_pool.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, 'a.md', 'sha256:abc', 'openai/text-embedding-3-small')",
        ws_id,
    )
    return admin_dsn


@pytest.mark.asyncio
async def test_reindex_no_indexer_change_creates_pending(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = await _create_with_doc(pg_container, session_pool, "ws_reindex_same")

    job = await reindex_workspace(
        name="ws_reindex_same",
        new_indexer=None,
        confirm=False,
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
    )
    assert job["status"] == "pending"
    assert job["triggered_by"] == "manual"


@pytest.mark.asyncio
async def test_reindex_indexer_change_without_confirm_raises_409(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = await _create_with_doc(pg_container, session_pool, "ws_reindex_409")

    with pytest.raises(IndexerChangeRequiresReindex) as exc_info:
        await reindex_workspace(
            name="ws_reindex_409",
            new_indexer=IndexerSpec(provider="voyage", model="voyage-3", api_key_ref="vk"),
            confirm=False,
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=_Resolver(),  # type: ignore[arg-type]
        )
    assert exc_info.value.documents_count == 1


@pytest.mark.asyncio
async def test_reindex_indexer_change_with_confirm_recreates_table_and_invalidates_docs(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = await _create_with_doc(pg_container, session_pool, "ws_reindex_ok")

    job = await reindex_workspace(
        name="ws_reindex_ok",
        new_indexer=IndexerSpec(provider="voyage", model="voyage-3", api_key_ref="vk"),
        confirm=True,
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
    )
    assert job["status"] == "pending"
    assert job["triggered_by"] == "reindex_indexer_change"

    # indexer_configs mis à jour
    ic = await session_pool.fetchrow(
        "SELECT provider, model, dimension, api_key_ref FROM indexer_configs ic "
        "JOIN workspaces w ON w.id = ic.workspace_id WHERE w.name='ws_reindex_ok'"
    )
    assert ic is not None
    assert ic["provider"] == "voyage"
    assert ic["model"] == "voyage-3"
    assert ic["dimension"] == 1024
    assert ic["api_key_ref"] == "vk"

    # indexed_documents purgés
    count = await session_pool.fetchval(
        "SELECT COUNT(*) FROM indexed_documents d JOIN workspaces w ON w.id=d.workspace_id "
        "WHERE w.name='ws_reindex_ok'"
    )
    assert count == 0

    # Table embeddings recréée avec la nouvelle dimension
    ws_dsn = derive_workspace_dsn(admin_dsn, "rag_ws_reindex_ok")
    ws_conn = await asyncpg.connect(ws_dsn)
    try:
        dim = await ws_conn.fetchval(
            "SELECT a.atttypmod FROM pg_attribute a "
            "JOIN pg_class c ON c.oid = a.attrelid "
            "WHERE c.relname='embeddings' AND a.attname='embedding'"
        )
    finally:
        await ws_conn.close()
    assert dim == 1024


@pytest.mark.asyncio
async def test_reindex_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound):
        await reindex_workspace(
            name="absent",
            new_indexer=None,
            confirm=False,
            config_pool=session_pool,
            admin_dsn="postgresql://x:y@z:5432/postgres",
            resolver=_Resolver(),  # type: ignore[arg-type]
            default_vault_name="rag",
        )
