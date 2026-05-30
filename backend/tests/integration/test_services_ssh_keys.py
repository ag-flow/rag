from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport
from rag.services.ssh_keys import (
    DuplicateSshKeyError,
    delete_ssh_key,
    generate_ssh_key,
    import_ssh_key,
    list_ssh_keys,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

_SAMPLE_PRIVATE_KEY = "-----BEGIN OPENSSH PRIVATE KEY-----\nfake_private_key_data\n-----END OPENSSH PRIVATE KEY-----\n"
_SAMPLE_PUBLIC_KEY = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIHRlc3RfdGVzdA== test@test"


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


async def test_import_and_list(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool)
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="deploy-test",
                    name="Deploy test",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    assert created.key_id == "deploy-test"
    assert created.name == "Deploy test"
    assert created.public_key == _SAMPLE_PUBLIC_KEY
    assert created.passphrase_protected is False
    assert created.harpo_path == "${vault://v1:/ssh/deploy-test/private_key}"
    mock_client.set_secret.assert_called_once_with(
        "/ssh/deploy-test/private_key", _SAMPLE_PRIVATE_KEY
    )

    async with pool.acquire() as conn:
        keys = await list_ssh_keys(conn, vault_id=vault["id"])
    assert len(keys) == 1
    assert keys[0].key_id == "deploy-test"


async def test_import_with_passphrase(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v2")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="enc-key",
                    name="Encrypted",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                    passphrase="secret123",
                ),
            )

    assert created.passphrase_protected is True


async def test_generate_ed25519(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v3")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-ed25519", name="Generated Ed25519", key_type="ed25519"),
            )

    assert created.key_type == "ed25519"
    assert created.public_key.startswith("ssh-ed25519 ")
    mock_client.set_secret.assert_called_once()
    _, private_pem = mock_client.set_secret.call_args[0]
    assert "BEGIN OPENSSH PRIVATE KEY" in private_pem


async def test_generate_rsa4096(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v4")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-rsa", name="Generated RSA", key_type="rsa-4096"),
            )

    assert created.key_type == "rsa-4096"
    assert created.public_key.startswith("ssh-rsa ")


async def test_generate_ecdsa256(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v5")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            created = await generate_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyGenerate(key_id="gen-ecdsa", name="Generated ECDSA", key_type="ecdsa-256"),
            )

    assert created.key_type == "ecdsa-256"
    assert created.public_key.startswith("ecdsa-sha2-nistp256 ")


async def test_duplicate_key_id_raises(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v6")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        async with pool.acquire() as conn:
            await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="dup",
                    name="First",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    with patch("rag.services.ssh_keys.HarpocrateVaultClient"):
        with pytest.raises(DuplicateSshKeyError):
            async with pool.acquire() as conn:
                await import_ssh_key(
                    conn,
                    vault=vault,
                    vault_svc=svc,
                    req=SshKeyImport(
                        key_id="dup",
                        name="Second",
                        private_key=_SAMPLE_PRIVATE_KEY,
                        public_key=_SAMPLE_PUBLIC_KEY,
                    ),
                )


async def test_delete_ssh_key(pool: asyncpg.Pool) -> None:
    vault = await _seed_vault(pool, "v7")
    svc = _mock_vault_svc()

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            created = await import_ssh_key(
                conn,
                vault=vault,
                vault_svc=svc,
                req=SshKeyImport(
                    key_id="del-me",
                    name="To delete",
                    private_key=_SAMPLE_PRIVATE_KEY,
                    public_key=_SAMPLE_PUBLIC_KEY,
                ),
            )

    with patch("rag.services.ssh_keys.HarpocrateVaultClient") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client

        async with pool.acquire() as conn:
            deleted = await delete_ssh_key(
                conn,
                key_id=str(created.id),
                vault=vault,
                vault_svc=svc,
            )

    assert deleted is True
    mock_client.delete_secret.assert_called_once()

    async with pool.acquire() as conn:
        keys = await list_ssh_keys(conn, vault_id=vault["id"])
    assert keys == []
