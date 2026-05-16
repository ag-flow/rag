from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.secrets.exceptions import VaultNotFoundError
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


async def _seed(svc, conn, **req_overrides):
    await conn.execute("DELETE FROM harpocrate_vaults")
    async with conn.transaction():
        return await svc.create(conn, _create_req(**req_overrides))


class _FakeHttpResp:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeSdkError(Exception):
    def __init__(self, status_code: int) -> None:
        super().__init__(f"status={status_code}")
        self.response = _FakeHttpResp(status_code)


@pytest.mark.asyncio
async def test_test_connection_returns_ok_when_secret_resolved(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn, probe_path="known/secret")
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.return_value = "ok"
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is True
    assert "résolu" in result.detail
    assert result.probe_path_used == "known/secret"


@pytest.mark.asyncio
async def test_test_connection_401_returns_ko(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn, probe_path="known/secret")
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.side_effect = _FakeSdkError(401)
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is False
    assert "auth refusée" in result.detail


@pytest.mark.asyncio
async def test_test_connection_403_returns_ko(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn, probe_path="known/secret")
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.side_effect = _FakeSdkError(403)
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is False
    assert "auth refusée" in result.detail


@pytest.mark.asyncio
async def test_test_connection_404_with_probe_path_is_ko(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn, probe_path="known/secret")
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.side_effect = _FakeSdkError(404)
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is False
    assert "introuvable" in result.detail


@pytest.mark.asyncio
async def test_test_connection_404_without_probe_path_is_ok(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    """probe_path=None : on classifie 404 sur __probe__ comme 'auth ok'."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)  # probe_path default = None
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.side_effect = _FakeSdkError(404)
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is True
    assert "auth ok" in result.detail
    assert result.probe_path_used == "__probe__"


@pytest.mark.asyncio
async def test_test_connection_raises_when_vault_absent(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    from uuid import uuid4

    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        with pytest.raises(VaultNotFoundError):
            await svc.test_connection(conn, uuid4())


@pytest.mark.asyncio
async def test_test_connection_unknown_error_returns_ko(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    """Erreur sans status_code (réseau, timeout) → ok=False, message générique."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn, probe_path="known/secret")
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.get_secret.side_effect = ConnectionError("timeout")
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is False
    assert "erreur SDK" in result.detail or "ConnectionError" in result.detail
