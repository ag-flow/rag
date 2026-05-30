from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa

from rag.schemas.ssh_keys import SshKeyGenerate, SshKeyImport, SshKeyOut
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateSshKeyError(Exception):
    pass


class SshKeyNotFoundError(Exception):
    pass


def _build_secret_path(key_id: str) -> str:
    return f"/ssh/{key_id}/private_key"


def _build_vault_ref(vault_name: str, key_id: str) -> str:
    return build_ref(vault_name, _build_secret_path(key_id))


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


def _generate_key_pair(key_type: str) -> tuple[str, str]:
    """Retourne (private_pem, public_openssh)."""
    if key_type == "ed25519":
        private: Any = ed25519.Ed25519PrivateKey.generate()
    elif key_type == "rsa-4096":
        private = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    elif key_type == "ecdsa-256":
        private = ec.generate_private_key(ec.SECP256R1())
    else:
        raise ValueError(f"Unsupported key_type: {key_type!r}")

    private_pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.OpenSSH,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()

    public_ssh = private.public_key().public_bytes(
        encoding=serialization.Encoding.OpenSSH,
        format=serialization.PublicFormat.OpenSSH,
    ).decode()

    return private_pem, public_ssh


async def list_ssh_keys(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[SshKeyOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, name, key_type, public_key, passphrase_protected, "
        "harpo_path, created_at "
        "FROM ssh_keys WHERE vault_id = $1::uuid ORDER BY key_id",
        vault_id,
    )
    return [SshKeyOut.model_validate(dict(r)) for r in rows]


async def import_ssh_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: SshKeyImport,
) -> SshKeyOut:
    secret_path = _build_secret_path(req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.key_id)
    passphrase_protected = req.passphrase is not None and len(req.passphrase) > 0

    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, req.private_key)

    try:
        row = await conn.fetchrow(
            "INSERT INTO ssh_keys "
            "(key_id, name, key_type, public_key, passphrase_protected, vault_id, harpo_path) "
            "VALUES ($1, $2, 'imported', $3, $4, $5::uuid, $6) "
            "RETURNING id, key_id, name, key_type, public_key, passphrase_protected, "
            "harpo_path, created_at",
            req.key_id,
            req.name,
            req.public_key,
            passphrase_protected,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateSshKeyError(
            f"key_id={req.key_id!r} already exists in this vault"
        ) from exc

    log.info("ssh_key.imported", vault_id=vault["id"], key_id=req.key_id)
    return SshKeyOut.model_validate(dict(row))


async def generate_ssh_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: SshKeyGenerate,
) -> SshKeyOut:
    secret_path = _build_secret_path(req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.key_id)

    private_pem, public_ssh = await asyncio.to_thread(_generate_key_pair, req.key_type)

    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, private_pem)

    try:
        row = await conn.fetchrow(
            "INSERT INTO ssh_keys "
            "(key_id, name, key_type, public_key, passphrase_protected, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4, false, $5::uuid, $6) "
            "RETURNING id, key_id, name, key_type, public_key, passphrase_protected, "
            "harpo_path, created_at",
            req.key_id,
            req.name,
            req.key_type,
            public_ssh,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateSshKeyError(
            f"key_id={req.key_id!r} already exists in this vault"
        ) from exc

    log.info("ssh_key.generated", vault_id=vault["id"], key_id=req.key_id, key_type=req.key_type)
    return SshKeyOut.model_validate(dict(row))


async def delete_ssh_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM ssh_keys "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    _, secret_path = parse_ref(row["harpo_path"])
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, secret_path)

    await conn.execute("DELETE FROM ssh_keys WHERE id = $1::uuid", key_id)
    log.info("ssh_key.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
