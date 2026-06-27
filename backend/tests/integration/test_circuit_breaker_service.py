from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.circuit_breaker import (
    auto_close_expired_circuits,
    close_circuit,
    get_circuit,
    open_circuit,
)
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


@pytest.mark.asyncio
async def test_open_circuit_creates_entry(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="cb_svc_open1")

    await open_circuit(
        pool,
        workspace_id=ws_id,
        provider="openai",
        model="text-embedding-3-small",
        error_message="rate limited",
    )

    circuit = await get_circuit(pool, workspace_id=ws_id)
    assert circuit is not None
    assert circuit["provider"] == "openai"
    assert circuit["model"] == "text-embedding-3-small"
    assert circuit["error_message"] == "rate limited"
    assert circuit["open_until"] is not None


@pytest.mark.asyncio
async def test_open_circuit_idempotent_updates_message(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="cb_svc_open2")

    await open_circuit(
        pool,
        workspace_id=ws_id,
        provider="openai",
        model="text-embedding-3-small",
        error_message="error1",
    )
    c1 = await get_circuit(pool, workspace_id=ws_id)

    await open_circuit(
        pool,
        workspace_id=ws_id,
        provider="openai",
        model="text-embedding-3-small",
        error_message="error2",
    )
    c2 = await get_circuit(pool, workspace_id=ws_id)

    assert c1 is not None and c2 is not None
    assert c2["error_message"] == "error2"
    # open_until est prolongé lors du second open
    assert c2["open_until"] >= c1["open_until"]


@pytest.mark.asyncio
async def test_close_circuit_removes_entry(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="cb_svc_close1")

    await open_circuit(
        pool,
        workspace_id=ws_id,
        provider="openai",
        model="text-embedding-3-small",
        error_message="err",
    )
    assert await get_circuit(pool, workspace_id=ws_id) is not None

    closed = await close_circuit(pool, workspace_id=ws_id)
    assert closed is True
    assert await get_circuit(pool, workspace_id=ws_id) is None


@pytest.mark.asyncio
async def test_close_circuit_returns_false_when_absent(pool: asyncpg.Pool) -> None:
    ws_id = UUID("00000000-0000-0000-0000-000000000001")
    closed = await close_circuit(pool, workspace_id=ws_id)
    assert closed is False


@pytest.mark.asyncio
async def test_auto_close_expired_removes_expired(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        ws_expired = await seed_workspace(conn, name="cb_svc_exp1")
        ws_future = await seed_workspace(conn, name="cb_svc_exp2")

        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message, open_until)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err',"
            " now() - interval '1 minute')",
            ws_expired,
        )
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message, open_until)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err',"
            " now() + interval '1 hour')",
            ws_future,
        )

    n = await auto_close_expired_circuits(pool)
    assert n == 1

    assert await get_circuit(pool, workspace_id=ws_expired) is None
    assert await get_circuit(pool, workspace_id=ws_future) is not None


@pytest.mark.asyncio
async def test_auto_close_skips_null_open_until(pool: asyncpg.Pool) -> None:
    """Un circuit avec open_until=NULL (fermeture manuelle uniquement)
    ne doit pas etre auto-ferme."""
    async with pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="cb_svc_null")
        await conn.execute(
            "INSERT INTO indexer_circuit_breakers"
            " (workspace_id, provider, model, error_message, open_until)"
            " VALUES ($1, 'openai', 'text-embedding-3-small', 'err', NULL)",
            ws_id,
        )

    n = await auto_close_expired_circuits(pool)
    assert n == 0
    assert await get_circuit(pool, workspace_id=ws_id) is not None
