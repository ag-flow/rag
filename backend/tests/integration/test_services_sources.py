from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.api.errors import (
    RefNotFoundInVault,
    SourceNotFound,
    WorkspaceNotFound,
)
from rag.db.migrations import run_migrations
from rag.schemas.admin import (
    IndexerSpec,
    SourceCreateRequest,
    SourceUpdateRequest,
    WorkspaceCreateRequest,
)
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.secrets.resolver import VaultLookupFailed
from rag.services.sources import add_source, delete_source, list_sources, update_source
from rag.services.workspaces import create_workspace
from tests.integration._git_fixture import make_bare_repo_with_commits

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _Resolver:
    def __init__(self, known: set[str]) -> None:
        self._known = known

    async def resolve_with_retry(self, ref: str) -> str:
        m = re.fullmatch(r"\$\{vault://[^:]+:([^}]+)\}", ref)
        assert m
        logical = m.group(1)
        if logical not in self._known:
            raise VaultLookupFailed(f"no {logical}")
        return "tok-x"


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


async def _setup_ws(pg_container: str, session_pool: asyncpg.Pool, name: str) -> _Resolver:
    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"
    resolver = _Resolver({"k", "github_token"})
    await create_workspace(
        request=WorkspaceCreateRequest(
            name=name,
            api_key_vault="rag",
            indexer=IndexerSpec(provider="openai", model="text-embedding-3-small", api_key_ref="k"),
        ),
        config_pool=session_pool,
        admin_dsn=admin_dsn,
        resolver=resolver,  # type: ignore[arg-type]
        harpocrate_vaults_service=_make_harpo_service(),
    )
    return resolver


@pytest.mark.asyncio
async def test_add_source_git_inserts_row(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_a")

    src = await add_source(
        workspace_name="ws_src_a",
        request=SourceCreateRequest(
            type="git",
            config={
                "url": "https://github.com/gael/harpocrate",
                "branch": "main",
                "auth_ref": "github_token",
                "include": ["**/*.md"],
                "exclude": [],
            },
        ),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
        default_vault_name="rag",
    )
    assert src["type"] == "git"
    assert src["config"]["url"] == "https://github.com/gael/harpocrate"

    rows = await list_sources(session_pool, workspace_name="ws_src_a")
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_add_source_workspace_not_found(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = _Resolver({"github_token"})
    with pytest.raises(WorkspaceNotFound):
        await add_source(
            workspace_name="absent",
            request=SourceCreateRequest(
                type="git",
                config={"url": "https://github.com/x/y", "auth_ref": "github_token"},
            ),
            config_pool=session_pool,
            resolver=resolver,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_add_source_auth_ref_not_in_vault_raises(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_b")
    # On retire github_token de la ref connue pour ce test :
    resolver._known.discard("github_token")  # type: ignore[attr-defined]

    with pytest.raises(RefNotFoundInVault):
        await add_source(
            workspace_name="ws_src_b",
            request=SourceCreateRequest(
                type="git",
                config={"url": "https://github.com/x/y", "auth_ref": "github_token"},
            ),
            config_pool=session_pool,
            resolver=resolver,  # type: ignore[arg-type]
        )


@pytest.mark.asyncio
async def test_add_source_no_auth_ref_does_not_resolve(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """Source publique sans auth_ref : pas de validation Harpocrate, OK."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_pub")
    src = await add_source(
        workspace_name="ws_src_pub",
        request=SourceCreateRequest(
            type="git",
            config={"url": "https://github.com/public/repo", "branch": "main"},
        ),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
        default_vault_name="rag",
    )
    assert src["type"] == "git"


@pytest.mark.asyncio
async def test_delete_source_removes_row(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_del")
    src = await add_source(
        workspace_name="ws_src_del",
        request=SourceCreateRequest(
            type="git",
            config={"url": "https://github.com/x/y", "auth_ref": "github_token"},
        ),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
        default_vault_name="rag",
    )

    await delete_source(workspace_name="ws_src_del", source_id=src["id"], config_pool=session_pool)
    assert await list_sources(session_pool, workspace_name="ws_src_del") == []


@pytest.mark.asyncio
async def test_delete_source_not_found_raises(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    import uuid

    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_src_404")
    with pytest.raises(SourceNotFound):
        await delete_source(
            workspace_name="ws_src_404",
            source_id=str(uuid.uuid4()),
            config_pool=session_pool,
        )


@pytest.mark.asyncio
async def test_add_source_sets_next_sync_at_to_now(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    """M3 : à la création d'une source, next_sync_at doit être posé à now()
    pour déclencher le premier sync au prochain cycle du worker."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_src_next_sync")

    src = await add_source(
        workspace_name="ws_src_next_sync",
        request=SourceCreateRequest(
            type="git",
            config={"url": "https://github.com/x/y", "auth_ref": "github_token"},
        ),
        config_pool=session_pool,
        resolver=resolver,  # type: ignore[arg-type]
        default_vault_name="rag",
    )

    next_at_offset = await session_pool.fetchval(
        "SELECT EXTRACT(EPOCH FROM (next_sync_at - now())) "
        "FROM workspace_sources WHERE id=$1::uuid",
        src["id"],
    )
    # next_sync_at devrait être quasi maintenant (±5s)
    assert -5 <= float(next_at_offset) <= 5


@pytest.mark.asyncio
async def test_add_source_empty_branch_detects_default(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None, tmp_path: Path
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_a")
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    src = await add_source(
        workspace_name="ws_branch_a",
        request=SourceCreateRequest(
            name="repo1",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={"url": f"file://{bare}", "include": ["**/*.md"], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "master"
    assert src["branch_warning"] is None


@pytest.mark.asyncio
async def test_add_source_unreachable_falls_back_to_main_with_warning(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_b")
    src = await add_source(
        workspace_name="ws_branch_b",
        request=SourceCreateRequest(
            name="repo2",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={
                "url": "https://example.invalid/x/y.git",
                "include": ["**/*.md"],
                "exclude": [],
            },
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "main"
    assert src["branch_warning"] is not None


@pytest.mark.asyncio
async def test_add_source_explicit_branch_no_detection(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await _setup_ws(pg_container, session_pool, "ws_branch_c")
    src = await add_source(
        workspace_name="ws_branch_c",
        request=SourceCreateRequest(
            name="repo3",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={
                "url": "https://example.invalid/x/y.git",
                "branch": "develop",
                "include": [],
                "exclude": [],
            },
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    assert src["config"]["branch"] == "develop"
    assert src["branch_warning"] is None


@pytest.mark.asyncio
async def test_update_source_empty_branch_redetects(
    pg_container: str, session_pool: asyncpg.Pool, cleanup_ws_dbs: None, tmp_path: Path
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    resolver = await _setup_ws(pg_container, session_pool, "ws_branch_upd")
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    created = await add_source(
        workspace_name="ws_branch_upd",
        request=SourceCreateRequest(
            name="repo-upd",
            type="git",
            api_key_vault="rag",
            auth_value=None,
            config={"url": f"file://{bare}", "branch": "main", "include": [], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
    )
    updated = await update_source(
        workspace_name="ws_branch_upd",
        source_id=created["id"],
        request=SourceUpdateRequest(
            auth_value=None,
            config={"url": f"file://{bare}", "include": [], "exclude": []},
        ),
        config_pool=session_pool,
        harpocrate_vaults_service=_make_harpo_service(),
        resolver=resolver,  # type: ignore[arg-type]
    )
    assert updated["config"]["branch"] == "master"
    assert updated["branch_warning"] is None
