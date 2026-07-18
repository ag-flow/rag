from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER_A = "7" * 64
OWNER_B = "8" * 64


def _set_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")


def _create_req(name: str, **overrides: object) -> VaultCreateRequest:
    payload: dict = {
        "name": name,
        "label": f"Coffre {name}",
        "base_url": "https://harpocrate.test",
        "api_key_id": f"k-{name}",
        "api_key": "pas-un-jwt",
        "is_default": False,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


@pytest.mark.asyncio
async def test_expiries_resilient_and_owner_scoped(
    session_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Agrégat best-effort : token illisible → None (pas d'échec), et seul
    le périmètre du caller (défaut + ses coffres) est remonté."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            mine = await svc.create(conn, _create_req("exp-mine"))
            await conn.execute(
                "UPDATE harpocrate_vaults SET owner_id=$1 WHERE id=$2", OWNER_A, mine.id
            )
            other = await svc.create(conn, _create_req("exp-other"))
            await conn.execute(
                "UPDATE harpocrate_vaults SET owner_id=$1 WHERE id=$2", OWNER_B, other.id
            )

        expiries = await svc.list_key_expiries(conn, OWNER_A)
    names = {e.name for e in expiries}
    assert "exp-mine" in names
    assert "exp-other" not in names  # coffre d'un autre owner, non défaut
    entry = next(e for e in expiries if e.name == "exp-mine")
    assert entry.api_key_expires_at is None  # token non décodable → pas d'erreur


@pytest.mark.asyncio
async def test_expiries_reads_token_exp_locally(
    session_pool: asyncpg.Pool, monkeypatch: pytest.MonkeyPatch
) -> None:
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    expires = datetime(2026, 9, 1, tzinfo=UTC)

    fake_client = MagicMock()
    fake_client.token_info.return_value = MagicMock(expires_at_dt=expires)

    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        async with conn.transaction():
            vault = await svc.create(conn, _create_req("exp-jwt"))
            await conn.execute(
                "UPDATE harpocrate_vaults SET owner_id=$1 WHERE id=$2", OWNER_A, vault.id
            )
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient", return_value=fake_client
        ):
            expiries = await svc.list_key_expiries(conn, OWNER_A)

    entry = next(e for e in expiries if e.name == "exp-jwt")
    assert entry.api_key_expires_at == expires
    fake_client.token_info.assert_called_once()
