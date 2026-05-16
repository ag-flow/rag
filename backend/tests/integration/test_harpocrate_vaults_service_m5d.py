from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

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
    monkeypatch.setenv(
        "RAG_POSTGRES_ADMIN_URL",
        "postgresql://u:p@localhost:5432/postgres",
    )
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )


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


async def _seed(svc, conn, **overrides):
    await conn.execute("DELETE FROM harpocrate_vaults")
    async with conn.transaction():
        return await svc.create(conn, _create_req(**overrides))


@pytest.mark.asyncio
async def test_get_wallet_info_combines_whoami_and_info(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        wallet_id = uuid4()
        expires = datetime(2027, 1, 1, tzinfo=UTC)
        with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mock_client:
            instance = MagicMock()
            instance.whoami.return_value = MagicMock(
                api_key_id="k-001",
                permissions=["read", "write"],
                expires_at=expires,
            )
            # MagicMock(name=...) set le _mock_name interne (utilisé pour le repr),
            # pas un attribut .name. On set name après instanciation.
            wallet_mock = MagicMock(wallet_id=wallet_id)
            wallet_mock.name = "prod-wallet"
            instance.info.return_value = wallet_mock
            mock_client.return_value = instance
            result = await svc.get_wallet_info(conn, seeded.id)
    assert result.wallet_id == wallet_id
    assert result.wallet_name == "prod-wallet"
    assert result.api_key_id == "k-001"
    assert result.permissions == ["read", "write"]
    assert result.api_key_expires_at == expires


@pytest.mark.asyncio
async def test_get_wallet_info_raises_when_vault_absent(
    session_pool: asyncpg.Pool,
    monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        with pytest.raises(VaultNotFoundError):
            await svc.get_wallet_info(conn, uuid4())
