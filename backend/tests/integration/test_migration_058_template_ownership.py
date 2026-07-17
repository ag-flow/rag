from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "a" * 64
OWNER_B = "b" * 64


async def _insert(
    conn: asyncpg.Connection,
    *,
    owner_id: str | None,
    name: str,
    language: str = "python",
    metadata_key: str = "documentation",
) -> None:
    await conn.execute(
        "INSERT INTO prompt_templates (owner_id, name, language, metadata_key, prompt) "
        "VALUES ($1, $2, $3, $4, 'Prompt {content}')",
        owner_id,
        name,
        language,
        metadata_key,
    )


@pytest.mark.asyncio
async def test_name_unique_per_library(session_pool: asyncpg.Pool) -> None:
    """Le nom est unique par bibliothèque (système / owner), plus globalement."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await _insert(conn, owner_id=OWNER_A, name="doc", metadata_key="k1")
        await _insert(conn, owner_id=OWNER_B, name="doc", metadata_key="k2")
        await _insert(conn, owner_id=None, name="doc", metadata_key="k3")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert(conn, owner_id=OWNER_A, name="doc", metadata_key="k4")


@pytest.mark.asyncio
async def test_metadata_key_unique_per_owner_and_language(session_pool: asyncpg.Pool) -> None:
    """La clé de métadonnée est unique par owner ET par langue : le partage
    inter-langues (modèle multi-langue de la migration 031) reste permis."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await _insert(conn, owner_id=OWNER_A, name="doc-py", language="python")
        await _insert(conn, owner_id=OWNER_A, name="doc-cs", language="csharp")
        await _insert(conn, owner_id=OWNER_B, name="doc-py", language="python")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert(conn, owner_id=OWNER_A, name="doc-py-2", language="python")


@pytest.mark.asyncio
async def test_system_metadata_key_unique(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await _insert(conn, owner_id=None, name="sys-doc-py", language="go")
        with pytest.raises(asyncpg.UniqueViolationError):
            await _insert(conn, owner_id=None, name="sys-doc-py-2", language="go")
