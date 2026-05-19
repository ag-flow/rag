from __future__ import annotations

import json
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
async def test_chunking_configs_check_strategy_rejects_unknown(
    session_pool: asyncpg.Pool,
) -> None:
    """La CHECK constraint rejette les stratégies non listées.

    Note : 'markdown' a été ajoutée à la liste autorisée par la migration 014
    (M9c-T1). On teste donc une stratégie volontairement inconnue.
    """
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_strategy_check")
        with pytest.raises(asyncpg.CheckViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
                "VALUES ($1, 'unknown_strategy', 2000, 200, 200)",
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
async def test_chunking_configs_extras_default_empty_dict(
    session_pool: asyncpg.Pool,
) -> None:
    """L'INSERT sans colonne `extras` doit produire `extras = {}` (default SQL)."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_extras_default")
        await conn.execute("DELETE FROM chunking_configs WHERE workspace_id = $1", ws_id)
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
        extras = await conn.fetchval(
            "SELECT extras FROM chunking_configs WHERE workspace_id = $1",
            ws_id,
        )
    # asyncpg renvoie JSONB en str ; on parse pour comparer au dict {}.
    assert json.loads(extras) == {}


@pytest.mark.asyncio
async def test_chunking_configs_extras_not_null(session_pool: asyncpg.Pool) -> None:
    """`extras = NULL` doit être rejeté par la contrainte NOT NULL."""
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_extras_not_null")
        await conn.execute("DELETE FROM chunking_configs WHERE workspace_id = $1", ws_id)
        with pytest.raises(asyncpg.NotNullViolationError):
            await conn.execute(
                "INSERT INTO chunking_configs "
                "(workspace_id, strategy, max_chars, min_chars, overlap_chars, extras) "
                "VALUES ($1, 'paragraph', 2000, 200, 200, NULL)",
                ws_id,
            )


@pytest.mark.asyncio
async def test_chunking_configs_populates_existing_workspaces(
    session_pool: asyncpg.Pool,
) -> None:
    """La migration 012 doit créer une row par défaut pour chaque workspace
    existant AVANT son application (vrai test du backfill).

    Stratégie : appliquer toutes les migrations, puis "rembobiner" la 012
    (DROP de la table + suppression de l'entrée schema_migrations). On seed
    alors les workspaces — ils existent comme si la 012 n'avait jamais tourné.
    On relance `run_migrations` qui ne réapplique que la 012 ; le backfill
    doit alors créer une row par workspace pré-existant.
    """
    await _reset(session_pool)
    await run_migrations(session_pool, MIGRATIONS_DIR)

    # Rewind : on ramène la base à l'état "post-011" (pas de table
    # chunking_configs, pas d'entrée schema_migrations pour la 012).
    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE chunking_configs")
        await conn.execute("DELETE FROM schema_migrations WHERE version = '012_chunking_configs'")

        # Seed deux workspaces "pré-existants" (avant que la 012 ne soit appliquée).
        ws_a = await seed_workspace(conn, name="ws_pop_a", api_key="pop-a-key")
        ws_b = await seed_workspace(conn, name="ws_pop_b", api_key="pop-b-key")

        # Pré-condition : la table chunking_configs n'existe pas encore.
        exists = await conn.fetchval(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables "
            "WHERE table_name = 'chunking_configs')"
        )
        assert exists is False, "chunking_configs ne devrait pas exister avant la 012"

    # Applique la 012 (seule migration encore en attente).
    await run_migrations(session_pool, MIGRATIONS_DIR)

    async with session_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT workspace_id, strategy, max_chars, min_chars, overlap_chars, extras "
            "FROM chunking_configs WHERE workspace_id IN ($1, $2) "
            "ORDER BY workspace_id",
            ws_a,
            ws_b,
        )

    assert len(rows) == 2, "le backfill doit créer exactement 1 row par workspace pré-existant"
    for r in rows:
        assert r["strategy"] == "paragraph"
        assert r["max_chars"] == 2000
        assert r["min_chars"] == 200
        assert r["overlap_chars"] == 200
        assert json.loads(r["extras"]) == {}
