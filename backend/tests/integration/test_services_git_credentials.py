from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.git_credentials import GitCredentialCreate, GitCredentialUpdate
from rag.services.git_credentials import (
    DuplicateGitCredentialError,
    GitCredentialNotFoundError,
    GitCredentialReferencedError,
    create_git_credential,
    delete_git_credential,
    list_git_credentials,
    update_git_credential,
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

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="prod-pat",
                    label="GitHub prod",
                    host="github",
                    value="ghp_test",
                ),
            )

    assert created.key_id == "prod-pat"
    assert created.host == "github"
    assert created.scope_url is None
    assert created.harpo_path == "${vault://v1:/git/github/prod-pat}"
    mock_client.set_secret.assert_called_once_with("/git/github/prod-pat", "ghp_test")

    async with pool.acquire() as conn:
        keys = await list_git_credentials(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "prod-pat"


async def test_create_with_scope_url(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(
                    key_id="org-pat",
                    label="GitHub myorg",
                    host="github",
                    scope_url="https://github.com/myorg",
                    value="ghp_test2",
                ),
            )

    assert created.scope_url == "https://github.com/myorg"


async def test_create_duplicate_raises(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="dup", label="L", host="gitlab", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        with pytest.raises(DuplicateGitCredentialError):
            async with pool.acquire() as conn:
                await create_git_credential(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=GitCredentialCreate(key_id="dup", label="L2", host="gitlab", value="v2"),
                )


async def test_update_label_and_scope(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="k1", label="Old", host="gitea", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            updated = await update_git_credential(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
                req=GitCredentialUpdate(label="New", scope_url="https://gitea.example.com"),
            )

    assert updated is not None
    assert updated.label == "New"
    assert updated.scope_url == "https://gitea.example.com"


async def test_delete_unreferenced(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v5")
    svc = _mock_vault_svc()

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            created = await create_git_credential(
                conn,
                vault=vault,
                vault_svc=svc,
                req=GitCredentialCreate(key_id="del-me", label="L", host="github", value="v"),
            )

    with patch("rag.services.git_credentials.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        async with pool.acquire() as conn:
            deleted = await delete_git_credential(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_git_credentials(conn, vault_id=vault["id"])
    assert keys == []
