from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.user_profile import (
    IdentityTakenError,
    InvalidIdentityError,
    email_for_identity,
    get_or_create_user,
    update_profile,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

GUID = "0f8fad5b-d9cb-469f-a165-70867728950e"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM users WHERE email IN ('alice@example.com', 'bob@example.com')"
        )
    return session_pool


@pytest.mark.asyncio
async def test_auto_provision_and_idempotence(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        u = await get_or_create_user(conn, email="alice@example.com", username="alice")
        assert u["identity"] is None
        u2 = await get_or_create_user(conn, email="alice@example.com")
        assert u2["id"] == u["id"]


@pytest.mark.asyncio
async def test_set_identity_and_obo_matching(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await get_or_create_user(conn, email="alice@example.com", username="alice")
        updated = await update_profile(
            conn, current_email="alice@example.com", identity=GUID
        )
        assert updated["identity"] == GUID

    # Matching OBO (v6) : GUID → email ; inconnu → None (repli clé, fail-safe).
    assert await email_for_identity(pool, GUID) == "alice@example.com"
    assert await email_for_identity(pool, "unknown-guid-123") is None


@pytest.mark.asyncio
async def test_identity_unique_and_clear(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await get_or_create_user(conn, email="alice@example.com", username="alice")
        await update_profile(conn, current_email="alice@example.com", identity=GUID)
        await get_or_create_user(conn, email="bob@example.com", username="bob")

        with pytest.raises(IdentityTakenError):
            await update_profile(conn, current_email="bob@example.com", identity=GUID)

        # Effacement : "" → NULL.
        cleared = await update_profile(conn, current_email="alice@example.com", identity="")
        assert cleared["identity"] is None


@pytest.mark.asyncio
async def test_identity_format_validated(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await get_or_create_user(conn, email="alice@example.com", username="alice")
        with pytest.raises(InvalidIdentityError):
            await update_profile(
                conn, current_email="alice@example.com", identity="a b c"
            )
