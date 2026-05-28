from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.webhooks import (
    create_webhook,
    delete_webhook,
    list_webhooks,
    patch_webhook,
    patch_webhook_header,
)
from rag.api.errors import ReservedHeader, WebhookNotFound, WorkspaceNotFound
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


async def test_create_and_list_webhook(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws1")

    created = await create_webhook(
        pool,
        workspace_name="ws1",
        name="hook1",
        url="https://example.com/hook",
        enabled=True,
        headers=[{"name": "X-Api-Key", "value": "secret", "vault": None, "enabled": True}],
        resolver=None,
    )
    assert created["name"] == "hook1"
    assert len(created["headers"]) == 1
    assert created["headers"][0]["value"] is None  # value non retournée

    hooks = await list_webhooks(pool, workspace_name="ws1")
    assert len(hooks) == 1
    assert hooks[0]["id"] == created["id"]


async def test_create_webhook_reserved_header_raises(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws2")

    with pytest.raises(ReservedHeader):
        await create_webhook(
            pool,
            workspace_name="ws2",
            name="hook2",
            url="https://x.com",
            enabled=True,
            headers=[{"name": "X-Correlation-ID", "value": "v", "vault": None, "enabled": True}],
            resolver=None,
        )


async def test_patch_webhook_enabled(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws3")

    wh = await create_webhook(
        pool,
        workspace_name="ws3",
        name="hook3",
        url="https://x.com",
        enabled=True,
        headers=[],
        resolver=None,
    )
    updated = await patch_webhook(pool, webhook_id=wh["id"], enabled=False)
    assert updated["enabled"] is False


async def test_delete_webhook(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws4")

    wh = await create_webhook(
        pool,
        workspace_name="ws4",
        name="hook4",
        url="https://x.com",
        enabled=True,
        headers=[],
        resolver=None,
    )
    await delete_webhook(pool, webhook_id=wh["id"], resolver=None)
    hooks = await list_webhooks(pool, workspace_name="ws4")
    assert hooks == []


async def test_webhook_not_found_on_patch(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await seed_workspace(conn, name="ws5")

    with pytest.raises(WebhookNotFound):
        await patch_webhook(
            pool,
            webhook_id="00000000-0000-0000-0000-000000000000",
            enabled=False,
        )
