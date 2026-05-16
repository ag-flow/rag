from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.secrets.exceptions import VaultNameAlreadyExistsError
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_required_env(monkeypatch) -> None:
    """Set les 5 champs requis de Settings + une DEK valide pour les tests."""
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")


def _create_req(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.mark.asyncio
async def test_list_all_empty(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.list_all(conn) == []


@pytest.mark.asyncio
async def test_get_by_id_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.get_by_id(conn, uuid4()) is None


@pytest.mark.asyncio
async def test_get_by_name_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.get_by_name(conn, "absent") is None


@pytest.mark.asyncio
async def test_get_default_returns_none_when_empty(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.get_default(conn) is None


@pytest.mark.asyncio
async def test_reveal_api_key_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.reveal_api_key(conn, uuid4()) is None


@pytest.mark.asyncio
async def test_create_persists_and_returns_summary(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            summary = await svc.create(conn, _create_req())
        assert summary.name == "rag"
        assert summary.is_default is True
        assert summary.id is not None
        revealed = await svc.reveal_api_key(conn, summary.id)
        assert revealed == "supersecretvalue123"


@pytest.mark.asyncio
async def test_create_duplicate_name_raises(session_pool: asyncpg.Pool, monkeypatch):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            await svc.create(conn, _create_req(name="dup"))
        with pytest.raises(VaultNameAlreadyExistsError):
            async with conn.transaction():
                await svc.create(conn, _create_req(name="dup", api_key_id="k-002"))


@pytest.mark.asyncio
async def test_create_second_default_demotes_previous(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_required_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            first = await svc.create(conn, _create_req(name="first", is_default=True))
        async with conn.transaction():
            second = await svc.create(
                conn,
                _create_req(name="second", api_key_id="k-002", is_default=True),
            )
        refreshed_first = await svc.get_by_id(conn, first.id)
        assert refreshed_first is not None
        assert refreshed_first.is_default is False
        assert second.is_default is True
