from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.provider_api_keys import ProviderApiKeyCreate, ProviderApiKeyUpdate
from rag.services.provider_api_keys import (
    DuplicateProviderKeyError,
    create_provider_key,
    delete_provider_key,
    list_provider_keys,
    update_provider_key,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
    return session_pool


async def _seed_vault(pool: asyncpg.Pool, name: str = "v1") -> dict:
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "INSERT INTO harpocrate_vaults "
            "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default) "
            "VALUES (gen_random_uuid(), $1, $1, 'https://h.io', 'kid', 'enc', false) "
            "RETURNING id, name",
            name,
        )
        return {"id": str(row["id"]), "name": row["name"], "base_url": "https://h.io"}


def _mock_vault_svc(api_key: str = "tok") -> MagicMock:
    svc = MagicMock()
    svc.reveal_api_key = AsyncMock(return_value=api_key)
    return svc


async def test_create_and_list(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool)
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_client_cls:
        mock_client = MagicMock()
        mock_client_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="prod-openai",
                    label="OpenAI Prod",
                    provider="openai",
                    value="sk-test",
                ),
            )

    assert created.key_id == "prod-openai"
    assert created.harpo_path == "/v1/openai/prod-openai"
    mock_client.set_secret.assert_called_once_with("/v1/openai/prod-openai", "sk-test")

    async with pool.acquire() as conn:
        keys = await list_provider_keys(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "prod-openai"


async def test_create_duplicate_409(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="dup", label="Dup", provider="openai", value="v"
                ),
            )

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        with pytest.raises(DuplicateProviderKeyError):
            async with pool.acquire() as conn:
                await create_provider_key(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=ProviderApiKeyCreate(
                        key_id="dup", label="Dup2", provider="openai", value="v2"
                    ),
                )


async def test_update_label(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="k1", label="Old Label", provider="voyage", value="v"
                ),
            )

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyUpdate(label="New Label"),
            )

    assert updated is not None
    assert updated.label == "New Label"


async def test_delete_unreferenced(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="del-me", label="L", provider="openai", value="v"
                ),
            )

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            deleted = await delete_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_provider_keys(conn, vault_id=vault["id"])
    assert keys == []


async def test_create_with_valid_days_sets_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v6")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="exp-key",
                    label="Expiring",
                    provider="openai",
                    value="sk-x",
                    valid_days=30,
                ),
            )

    assert created.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=30)
    assert abs((created.expires_at - expected).total_seconds()) < 5


async def test_create_without_valid_days_expires_at_is_none(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v7")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="no-exp",
                    label="No expiry",
                    provider="openai",
                    value="sk-x",
                ),
            )

    assert created.expires_at is None


async def test_update_valid_days_recalculates_expires_at(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v8")
    svc = _mock_vault_svc()

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_provider_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyCreate(
                    key_id="upd-exp",
                    label="L",
                    provider="openai",
                    value="sk-x",
                ),
            )

    assert created.expires_at is None

    with patch("rag.services.provider_api_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_provider_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=ProviderApiKeyUpdate(valid_days=60),
            )

    assert updated is not None
    assert updated.expires_at is not None
    expected = datetime.now(UTC) + timedelta(days=60)
    assert abs((updated.expires_at - expected).total_seconds()) < 5
