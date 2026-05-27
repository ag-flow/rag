from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.helpers import execute, fetch_all, fetch_one, transaction
from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_INSERT_WS_SQL = (
    "INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base) "
    "VALUES ($1, $2, $3, 'c', 'b')"
)


def _ref(name: str) -> str:
    return f"${{vault://test:{name}_apikey}}"


@pytest.fixture
async def migrated(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")
    return session_pool


@pytest.mark.asyncio
async def test_fetch_one_returns_row(migrated: asyncpg.Pool) -> None:
    await execute(
        migrated,
        _INSERT_WS_SQL,
        "w_helper",
        _ref("w_helper"),
        "fp_w_helper",
    )
    row = await fetch_one(migrated, "SELECT name FROM workspaces WHERE name = $1", "w_helper")
    assert row is not None
    assert row["name"] == "w_helper"


@pytest.mark.asyncio
async def test_fetch_one_returns_none_when_no_match(migrated: asyncpg.Pool) -> None:
    row = await fetch_one(migrated, "SELECT name FROM workspaces WHERE name = $1", "nope")
    assert row is None


@pytest.mark.asyncio
async def test_fetch_all_returns_list(migrated: asyncpg.Pool) -> None:
    await execute(migrated, _INSERT_WS_SQL, "a", _ref("a"), "fp_a")
    await execute(migrated, _INSERT_WS_SQL, "b", _ref("b"), "fp_b")
    rows = await fetch_all(migrated, "SELECT name FROM workspaces ORDER BY name")
    assert [r["name"] for r in rows] == ["a", "b"]


@pytest.mark.asyncio
async def test_transaction_commits(migrated: asyncpg.Pool) -> None:
    async with transaction(migrated) as conn:
        await conn.execute(_INSERT_WS_SQL, "tx_ok", _ref("tx_ok"), "fp_tx_ok")

    count = await fetch_one(migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_ok'")
    assert count is not None and count["c"] == 1


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_error(migrated: asyncpg.Pool) -> None:
    with pytest.raises(RuntimeError, match="forced"):
        async with transaction(migrated) as conn:
            await conn.execute(_INSERT_WS_SQL, "tx_rb", _ref("tx_rb"), "fp_tx_rb")
            raise RuntimeError("forced")

    count = await fetch_one(migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_rb'")
    assert count is not None and count["c"] == 0
