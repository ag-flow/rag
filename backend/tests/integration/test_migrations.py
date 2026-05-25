from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import MigrationError, list_applied, run_migrations


@pytest.fixture
def migrations_dir(tmp_path: Path) -> Path:
    """Construit un dossier de migrations factice pour les tests."""
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "000_schema_migrations.sql").write_text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"
    )
    (d / "001_first.sql").write_text("CREATE TABLE first_table (id INT PRIMARY KEY);")
    (d / "002_second.sql").write_text("CREATE TABLE second_table (id INT PRIMARY KEY);")
    return d


@pytest.mark.asyncio
async def test_run_migrations_applies_all(session_pool: asyncpg.Pool, migrations_dir: Path) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE"
        )

    await run_migrations(session_pool, migrations_dir)

    async with session_pool.acquire() as conn:
        applied = await conn.fetch("SELECT version FROM schema_migrations ORDER BY version")
        assert [r["version"] for r in applied] == [
            "000_schema_migrations",
            "001_first",
            "002_second",
        ]

        first = await conn.fetchval("SELECT to_regclass('public.first_table')::text")
        assert first == "first_table"


@pytest.mark.asyncio
async def test_run_migrations_idempotent(session_pool: asyncpg.Pool, migrations_dir: Path) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE"
        )

    await run_migrations(session_pool, migrations_dir)
    await run_migrations(session_pool, migrations_dir)

    async with session_pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM schema_migrations")
        assert count == 3


@pytest.mark.asyncio
async def test_list_applied(session_pool: asyncpg.Pool, migrations_dir: Path) -> None:
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DROP TABLE IF EXISTS first_table, second_table, schema_migrations CASCADE"
        )

    await run_migrations(session_pool, migrations_dir)
    versions = await list_applied(session_pool)
    assert versions == ["000_schema_migrations", "001_first", "002_second"]


@pytest.mark.asyncio
async def test_run_migrations_aborts_on_sql_error(
    session_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    d = tmp_path / "migrations"
    d.mkdir()
    (d / "000_schema_migrations.sql").write_text(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        "version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now());"
    )
    (d / "001_bad.sql").write_text("SELECT * FROM nonexistent_table;")

    async with session_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS schema_migrations CASCADE")

    with pytest.raises(MigrationError, match="001_bad"):
        await run_migrations(session_pool, d)

    async with session_pool.acquire() as conn:
        applied = await conn.fetch("SELECT version FROM schema_migrations")
        assert [r["version"] for r in applied] == ["000_schema_migrations"]
