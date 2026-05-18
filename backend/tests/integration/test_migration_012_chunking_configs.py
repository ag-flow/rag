from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _reset(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS chunking_configs, rerank_configs, indexer_configs, "
            "workspace_sources, index_jobs, indexed_documents, "
            "workspaces, harpocrate_vaults, model_dimensions, "
            "schema_migrations CASCADE"
        )


@pytest.mark.asyncio
async def test_chunking_configs_columns(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        cols = {
            r["column_name"]: r["data_type"]
            for r in await conn.fetch(
                "SELECT column_name, data_type FROM information_schema.columns "
                "WHERE table_name = 'chunking_configs'"
            )
        }
    expected = {
        "workspace_id",
        "strategy",
        "max_chars",
        "min_chars",
        "overlap_chars",
        "extras",
        "created_at",
        "updated_at",
    }
    assert expected.issubset(cols.keys()), f"missing: {expected - cols.keys()}"
    assert cols["workspace_id"] == "uuid"
    assert cols["strategy"] == "text"
    assert cols["max_chars"] == "integer"
    assert cols["extras"] == "jsonb"


@pytest.mark.asyncio
async def test_chunking_configs_fk_cascade(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_cascade")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        await conn.execute("DELETE FROM workspaces WHERE id = $1", ws_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_configs WHERE workspace_id = $1",
            ws_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_chunking_configs_check_strategy_paragraph_only(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_strategy_check")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'markdown', 2000, 200, 200)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_check_min_lt_max(session_pool: asyncpg.Pool) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_min_max")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'paragraph', 200, 200, 50)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_check_overlap_lt_max(
    session_pool: asyncpg.Pool,
) -> None:
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_overlap_max")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'paragraph', 500, 100, 500)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_populates_existing_workspaces(
    session_pool: asyncpg.Pool,
) -> None:
    """La migration crée une row par défaut pour chaque workspace existant."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    sql = (MIGRATIONS_DIR / "012_chunking_configs.sql").read_text(encoding="utf-8")
    insert_sql = sql[sql.index("INSERT INTO") :]

    async with session_pool.acquire() as conn:
        ws_a = await seed_workspace(conn, name="ws_pop_a", api_key="pop-a-key")
        ws_b = await seed_workspace(conn, name="ws_pop_b", api_key="pop-b-key")
        await conn.execute("DELETE FROM chunking_configs")
        await conn.execute(insert_sql)

        rows = await conn.fetch(
            "SELECT workspace_id, strategy, max_chars, min_chars, overlap_chars "
            "FROM chunking_configs WHERE workspace_id IN ($1, $2) "
            "ORDER BY workspace_id",
            ws_a,
            ws_b,
        )

    assert len(rows) == 2
    for r in rows:
        assert r["strategy"] == "paragraph"
        assert r["max_chars"] == 2000
        assert r["min_chars"] == 200
        assert r["overlap_chars"] == 200
