from __future__ import annotations

import asyncpg
import pytest

from rag.db.helpers import execute, fetch_all, fetch_one, transaction

# Schéma workspaces à HEAD : plus de colonnes api_key_* (retirées en 033),
# les clés d'accès sont au niveau utilisateur (053).
_INSERT_WS_SQL = "INSERT INTO workspaces (name, rag_cnx, rag_base) VALUES ($1, 'c', 'b')"


@pytest.mark.asyncio
async def test_fetch_one_returns_row(migrated: asyncpg.Pool) -> None:
    await execute(migrated, _INSERT_WS_SQL, "w_helper")
    row = await fetch_one(migrated, "SELECT name FROM workspaces WHERE name = $1", "w_helper")
    assert row is not None
    assert row["name"] == "w_helper"


@pytest.mark.asyncio
async def test_fetch_one_returns_none_when_no_match(migrated: asyncpg.Pool) -> None:
    row = await fetch_one(migrated, "SELECT name FROM workspaces WHERE name = $1", "nope")
    assert row is None


@pytest.mark.asyncio
async def test_fetch_all_returns_list(migrated: asyncpg.Pool) -> None:
    await execute(migrated, _INSERT_WS_SQL, "a")
    await execute(migrated, _INSERT_WS_SQL, "b")
    rows = await fetch_all(migrated, "SELECT name FROM workspaces ORDER BY name")
    assert [r["name"] for r in rows] == ["a", "b"]


@pytest.mark.asyncio
async def test_transaction_commits(migrated: asyncpg.Pool) -> None:
    async with transaction(migrated) as conn:
        await conn.execute(_INSERT_WS_SQL, "tx_ok")

    count = await fetch_one(migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_ok'")
    assert count is not None and count["c"] == 1


@pytest.mark.asyncio
async def test_transaction_rolls_back_on_error(migrated: asyncpg.Pool) -> None:
    with pytest.raises(RuntimeError, match="forced"):
        async with transaction(migrated) as conn:
            await conn.execute(_INSERT_WS_SQL, "tx_rb")
            raise RuntimeError("forced")

    count = await fetch_one(migrated, "SELECT COUNT(*) AS c FROM workspaces WHERE name = 'tx_rb'")
    assert count is not None and count["c"] == 0
