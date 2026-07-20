"""Isolation par propriétaire des workspaces (migration 068).

Un workspace appartient à son créateur (owner_id), comme les stratégies et les
prompts : visible/accessible seulement s'il est PARTAGÉ (owner NULL) ou possédé
par le caller. Couvre la liste/détail (admin) et la résolution owner-scopée
(point d'application commun).
"""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.workspaces import (
    WorkspaceNotFound,
    get_workspace,
    list_workspaces,
    resolve_owned_workspace_id,
)
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "a" * 64
OWNER_B = "b" * 64


async def _seed(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await seed_workspace(conn, name="ws_a", rag_base="rag_a", owner_id=OWNER_A)
        await seed_workspace(conn, name="ws_b", rag_base="rag_b", owner_id=OWNER_B)
        await seed_workspace(conn, name="ws_shared", rag_base="rag_shared", owner_id=None)


@pytest.mark.asyncio
async def test_list_scopes_to_owner_plus_shared(session_pool: asyncpg.Pool) -> None:
    await _seed(session_pool)
    names_a = {w["name"] for w in await list_workspaces(session_pool, owner_id=OWNER_A)}
    assert "ws_a" in names_a
    assert "ws_shared" in names_a
    assert "ws_b" not in names_a  # workspace de B invisible pour A


@pytest.mark.asyncio
async def test_get_other_owner_workspace_refused(session_pool: asyncpg.Pool) -> None:
    await _seed(session_pool)
    # A accède au sien et au partagé.
    assert (await get_workspace(session_pool, name="ws_a", owner_id=OWNER_A))["name"] == "ws_a"
    assert (await get_workspace(session_pool, name="ws_shared", owner_id=OWNER_A))["name"] == (
        "ws_shared"
    )
    # A ne peut PAS accéder à celui de B (introuvable).
    with pytest.raises(WorkspaceNotFound):
        await get_workspace(session_pool, name="ws_b", owner_id=OWNER_A)


@pytest.mark.asyncio
async def test_resolve_owned_workspace_id(session_pool: asyncpg.Pool) -> None:
    await _seed(session_pool)
    async with session_pool.acquire() as conn:
        assert await resolve_owned_workspace_id(conn, name="ws_a", owner_id=OWNER_A) is not None
        assert (
            await resolve_owned_workspace_id(conn, name="ws_shared", owner_id=OWNER_A) is not None
        )
        # Workspace de B : introuvable pour A.
        assert await resolve_owned_workspace_id(conn, name="ws_b", owner_id=OWNER_A) is None
