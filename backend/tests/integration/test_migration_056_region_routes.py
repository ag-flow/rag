from __future__ import annotations

from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.chunking_routing import load_region_routes

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _seed_strategy(conn: asyncpg.Connection, name: str) -> UUID:
    return await conn.fetchval(
        "INSERT INTO chunking_strategies (name, algo, params) "
        "VALUES ($1, 'prose', '{}'::jsonb) RETURNING id",
        name,
    )


@pytest.mark.asyncio
async def test_route_defaults_and_pk(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        strategy_id = await _seed_strategy(conn, "strat_routes_pk")
        await conn.execute(
            "INSERT INTO chunking_strategy_region_routes (strategy_id, region_type) "
            "VALUES ($1, 'code_fence')",
            strategy_id,
        )
        row = await conn.fetchrow(
            "SELECT qualifier, target_strategy_id, atomic, overflow_policy "
            "FROM chunking_strategy_region_routes WHERE strategy_id = $1",
            strategy_id,
        )
        assert (row["qualifier"], row["target_strategy_id"]) == ("*", None)
        assert (row["atomic"], row["overflow_policy"]) == (False, "keep_whole")
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategy_region_routes (strategy_id, region_type) "
                "VALUES ($1, 'code_fence')",
                strategy_id,
            )


@pytest.mark.asyncio
async def test_overflow_policy_check(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        strategy_id = await _seed_strategy(conn, "strat_routes_check")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_strategy_region_routes "
                "(strategy_id, region_type, overflow_policy) VALUES ($1, 'table', 'truncate')",
                strategy_id,
            )


@pytest.mark.asyncio
async def test_delete_strategy_cascades_but_target_is_protected(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        owner_id = await _seed_strategy(conn, "strat_routes_owner")
        target_id = await _seed_strategy(conn, "strat_routes_target")
        await conn.execute(
            "INSERT INTO chunking_strategy_region_routes "
            "(strategy_id, region_type, qualifier, target_strategy_id) "
            "VALUES ($1, 'code_fence', 'mermaid', $2)",
            owner_id,
            target_id,
        )
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("DELETE FROM chunking_strategies WHERE id = $1", target_id)
        await conn.execute("DELETE FROM chunking_strategies WHERE id = $1", owner_id)
        remaining = await conn.fetchval(
            "SELECT count(*) FROM chunking_strategy_region_routes WHERE strategy_id = $1",
            owner_id,
        )
        assert remaining == 0


@pytest.mark.asyncio
async def test_load_region_routes_returns_typed_routes(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        strategy_id = await _seed_strategy(conn, "strat_routes_load")
        target_id = await _seed_strategy(conn, "strat_routes_load_target")
        await conn.execute(
            "INSERT INTO chunking_strategy_region_routes "
            "(strategy_id, region_type, qualifier, target_strategy_id, atomic, overflow_policy) "
            "VALUES ($1, 'code_fence', 'mermaid', $2, false, 'parent_only'), "
            "($1, 'table', '*', NULL, true, 'keep_whole')",
            strategy_id,
            target_id,
        )
    routes = await load_region_routes(session_pool, strategy_id)
    assert len(routes) == 2
    fence = next(r for r in routes if r.region_type == "code_fence")
    assert fence.qualifier == "mermaid"
    assert fence.target_strategy_id == target_id
    assert fence.overflow_policy == "parent_only"
    table = next(r for r in routes if r.region_type == "table")
    assert (table.qualifier, table.atomic) == ("*", True)
