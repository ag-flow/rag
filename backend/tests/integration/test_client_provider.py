from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.secrets.client_provider import HarpocrateClientProvider
from rag.secrets.exceptions import VaultNotFoundError
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_env(monkeypatch, *, with_env_vault: bool = False) -> None:
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    if with_env_vault:
        monkeypatch.setenv("HARPOCRATE_API_TOKEN_RAG", "envtoken")
        monkeypatch.setenv("HARPOCRATE_API_URL_RAG", "https://h.env")
    else:
        monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
        monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)


def _create_req(**o):
    p = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    p.update(o)
    return VaultCreateRequest(**p)


@pytest.mark.asyncio
async def test_load_from_db_when_non_empty(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(conn, _create_req(name="dbvault"))

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as mock_client:
        mock_client.return_value = MagicMock()
        provider = HarpocrateClientProvider(Settings(), svc, session_pool)
        client = await provider.get_client("dbvault")
        assert client is not None
        assert await provider.get_default_vault_name() == "dbvault"


@pytest.mark.asyncio
async def test_fallback_env_when_db_empty(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch, with_env_vault=True)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as mock_client:
        mock_client.return_value = MagicMock()
        provider = HarpocrateClientProvider(Settings(), svc, session_pool)
        client = await provider.get_client("rag")
        assert client is not None
        assert await provider.get_default_vault_name() == "rag"


@pytest.mark.asyncio
async def test_get_default_first_alphabetical_in_env_fallback(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ZULU", "t1")
    monkeypatch.setenv("HARPOCRATE_API_URL_ZULU", "https://z")
    monkeypatch.setenv("HARPOCRATE_API_TOKEN_ALPHA", "t2")
    monkeypatch.setenv("HARPOCRATE_API_URL_ALPHA", "https://a")
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as mock_client:
        mock_client.return_value = MagicMock()
        provider = HarpocrateClientProvider(Settings(), svc, session_pool)
        assert await provider.get_default_vault_name() == "alpha"


@pytest.mark.asyncio
async def test_unknown_vault_name_raises(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")

    provider = HarpocrateClientProvider(Settings(), svc, session_pool)
    with pytest.raises(VaultNotFoundError):
        await provider.get_client("absent")


@pytest.mark.asyncio
async def test_invalidate_forces_reload(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(conn, _create_req(name="vone"))

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as mock_client:
        mock_client.return_value = MagicMock()
        provider = HarpocrateClientProvider(Settings(), svc, session_pool)
        await provider.get_client("vone")
        # Ajouter un 2e coffre puis invalider
        async with (
            session_pool.acquire() as conn,
            conn.transaction(),
        ):
            await svc.create(
                conn,
                _create_req(name="vtwo", api_key_id="k2", is_default=False),
            )
        provider.invalidate()
        client_v2 = await provider.get_client("vtwo")
        assert client_v2 is not None


@pytest.mark.asyncio
async def test_default_missing_when_no_is_default_in_db(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    """Table non vide mais aucun is_default=true → default_name=None."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            v = await svc.create(conn, _create_req(name="orphan", is_default=True))
        await conn.execute(
            "UPDATE harpocrate_vaults SET is_default = false WHERE id = $1",
            v.id,
        )

    with patch("rag.secrets.client_provider.HarpocrateVaultClient") as mock_client:
        mock_client.return_value = MagicMock()
        provider = HarpocrateClientProvider(Settings(), svc, session_pool)
        assert await provider.get_default_vault_name() is None
