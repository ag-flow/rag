from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path

import asyncpg
import pytest

from rag.api.errors import RefNotFoundInVault, WorkspaceNotFound
from rag.db.migrations import run_migrations
from rag.schemas.admin import (
    IndexerPatchSpec,
    IndexerSpec,
    WorkspaceCreateRequest,
    WorkspacePatchRequest,
)
from rag.secrets.resolver import VaultLookupFailed
from rag.services.workspaces import create_workspace, get_workspace, patch_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    def __init__(self, known: set[str]) -> None:
        self._known = known

    async def resolve_with_retry(self, ref: str) -> str:
        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        assert m
        logical = m.group(1)
        if logical not in self._known:
            raise VaultLookupFailed(f"no secret {logical}")
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
async def test_patch_api_key_ref_updates_indexer_config(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _Resolver({"old_key", "new_key"})

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_patch",
            indexer=IndexerSpec(
                provider="openai", model="text-embedding-3-small", api_key_ref="old_key"
            ),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=resolver,  # type: ignore[arg-type]
    )

    await patch_workspace(
        name="ws_patch",
        request=WorkspacePatchRequest(indexer=IndexerPatchSpec(api_key_ref="new_key")),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
    )

    detail = await get_workspace(session_pool, name="ws_patch")
    assert detail["indexer"]["api_key_ref"] == "new_key"  # type: ignore[index]


@pytest.mark.asyncio
async def test_patch_workspace_not_found_raises(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = _Resolver({"k"})
    with pytest.raises(WorkspaceNotFound):
        await patch_workspace(
            name="absent",
            request=WorkspacePatchRequest(indexer=IndexerPatchSpec(api_key_ref="k")),
            config_pool=session_pool,
            resolver=resolver,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_patch_workspace_new_ref_not_in_vault_raises(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _Resolver({"old_key"})

    await create_workspace(
        request=WorkspaceCreateRequest(
            name="ws_patch_bad",
            indexer=IndexerSpec(
                provider="openai", model="text-embedding-3-small", api_key_ref="old_key"
            ),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=resolver,  # type: ignore[arg-type]
    )

    with pytest.raises(RefNotFoundInVault):
        await patch_workspace(
            name="ws_patch_bad",
            request=WorkspacePatchRequest(indexer=IndexerPatchSpec(api_key_ref="nope")),
            config_pool=session_pool,
            resolver=resolver,  # type: ignore[arg-type]
        )
