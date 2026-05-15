from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.apikey import verify_api_key
from rag.services.workspaces import create_workspace, rotate_apikey

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    def resolve_with_retry(self, ref: str) -> str:
        assert re.fullmatch(r"\$\{vault://[^:]+:[^}]+\}", ref)
        return "sk-x"


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
async def test_rotate_apikey_returns_new_key_and_updates_hash(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    create_resp = await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_rotate",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=_Resolver(),  # type: ignore[arg-type]
    )
    old_key = create_resp["api_key"]

    new_key = await rotate_apikey(name="ws_rotate", config_pool=session_pool)
    assert new_key != old_key
    assert re.fullmatch(r"[A-Za-z0-9_-]{48}", new_key)

    row = await session_pool.fetchrow(
        "SELECT api_key_hash FROM workspaces WHERE name=$1", "ws_rotate"
    )
    assert row is not None
    assert verify_api_key(new_key, row["api_key_hash"]) is True
    assert verify_api_key(old_key, row["api_key_hash"]) is False


@pytest.mark.asyncio
async def test_rotate_apikey_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    with pytest.raises(WorkspaceNotFound):
        await rotate_apikey(name="absent", config_pool=session_pool)
