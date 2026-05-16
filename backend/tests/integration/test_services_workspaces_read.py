from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.workspaces import create_workspace, get_workspace, list_workspaces

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        assert m
        return "sk-stub"


@pytest.fixture
def cleanup_ws_dbs(pg_container: str) -> Iterator[None]:
    yield
    import asyncio

    async def _cleanup() -> None:
        admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
        admin = await asyncpg.connect(admin_dsn)
        try:
            rows = await admin.fetch(
                "SELECT datname FROM pg_database WHERE datname LIKE 'rag_ws_%'"
            )
            for r in rows:
                await admin.execute(f'DROP DATABASE IF EXISTS "{r["datname"]}" WITH (FORCE)')
        finally:
            await admin.close()

    asyncio.get_event_loop().run_until_complete(_cleanup())


@pytest.mark.asyncio
async def test_list_workspaces_empty(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    rows = await list_workspaces(session_pool)
    assert rows == []


@pytest.mark.asyncio
async def test_list_workspaces_includes_created(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    for name in ("ws_list_a", "ws_list_b"):
        await create_workspace(
            request=WorkspaceCreateRequest(
                name=name,
                indexer=IndexerSpec(
                    provider="openai", model="text-embedding-3-small", api_key_ref="k"
                ),
            ),
            config_pool=session_pool,
            admin_dsn=admin_dsn,
            resolver=_StubResolver(),  # type: ignore[arg-type]
        )

    rows = await list_workspaces(session_pool)
    names = {r["name"] for r in rows}
    assert {"ws_list_a", "ws_list_b"}.issubset(names)
    a = next(r for r in rows if r["name"] == "ws_list_a")
    assert a["sources_count"] == 0
    assert a["documents_count"] == 0
    assert a["last_indexed_at"] is None
    assert a["indexer"]["provider"] == "openai"


@pytest.mark.asyncio
async def test_get_workspace_returns_detail(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_detail",
            indexer=IndexerSpec(provider="voyage", model="voyage-3", api_key_ref="voyage_api_key"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_StubResolver(),  # type: ignore[arg-type]
    )

    detail = await get_workspace(session_pool, name="ws_detail")
    assert detail["name"] == "ws_detail"
    assert detail["indexer"]["provider"] == "voyage"
    assert detail["indexer"]["model"] == "voyage-3"
    assert detail["sources_count"] == 0


@pytest.mark.asyncio
async def test_get_workspace_not_found_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound) as exc_info:
        await get_workspace(session_pool, name="absent")
    assert exc_info.value.name == "absent"
