from __future__ import annotations

from pathlib import Path
from uuid import uuid4

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultUpdateRequest,
)
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_env(monkeypatch) -> None:
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


async def _seed_default(svc, conn):
    await conn.execute("DELETE FROM harpocrate_vaults")
    async with conn.transaction():
        return await svc.create(conn, _create_req())


@pytest.mark.asyncio
async def test_update_label_only(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed_default(svc, conn)
        updated = await svc.update(
            conn,
            seeded.id,
            VaultUpdateRequest(label="Nouveau libellé"),
        )
        assert updated is not None
        assert updated.label == "Nouveau libellé"
        assert updated.base_url == seeded.base_url
        assert updated.probe_path == seeded.probe_path


@pytest.mark.asyncio
async def test_update_probe_path_to_null(session_pool: asyncpg.Pool, monkeypatch):
    """probe_path = '' doit être un reset explicite à NULL via le validator."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed_default(svc, conn)
        # set un probe_path
        await svc.update(conn, seeded.id, VaultUpdateRequest(probe_path="some/path"))
        # reset via "" → validator transforme en None
        updated2 = await svc.update(conn, seeded.id, VaultUpdateRequest(probe_path=""))
        assert updated2 is not None
        assert updated2.probe_path is None


@pytest.mark.asyncio
async def test_update_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        result = await svc.update(conn, uuid4(), VaultUpdateRequest(label="x"))
        assert result is None


@pytest.mark.asyncio
async def test_rotate_api_key_changes_encrypted_value(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed_default(svc, conn)
        old_key = await svc.reveal_api_key(conn, seeded.id)
        updated = await svc.rotate_api_key(
            conn,
            seeded.id,
            VaultRotateApiKeyRequest(api_key_id="k-002", api_key="newsecretXYZ987"),
        )
        assert updated is not None
        assert updated.api_key_id == "k-002"
        new_key = await svc.reveal_api_key(conn, seeded.id)
        assert new_key == "newsecretXYZ987"
        assert new_key != old_key


@pytest.mark.asyncio
async def test_rotate_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        result = await svc.rotate_api_key(
            conn,
            uuid4(),
            VaultRotateApiKeyRequest(api_key_id="k", api_key="xxxxxxxxxxxx"),
        )
        assert result is None


@pytest.mark.asyncio
async def test_set_default_swaps_atomically(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        first = await _seed_default(svc, conn)
        async with conn.transaction():
            second = await svc.create(
                conn,
                _create_req(name="second", api_key_id="k-002", is_default=False),
            )
        updated = await svc.set_default(conn, second.id)
        assert updated is not None
        assert updated.is_default is True
        refreshed_first = await svc.get_by_id(conn, first.id)
        assert refreshed_first is not None
        assert refreshed_first.is_default is False


@pytest.mark.asyncio
async def test_set_default_returns_none_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.set_default(conn, uuid4()) is None


@pytest.mark.asyncio
async def test_delete_returns_true(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed_default(svc, conn)
        assert await svc.delete(conn, seeded.id) is True
        assert await svc.get_by_id(conn, seeded.id) is None


@pytest.mark.asyncio
async def test_delete_returns_false_when_absent(session_pool: asyncpg.Pool, monkeypatch):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        assert await svc.delete(conn, uuid4()) is False
