from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.git_credentials import (
    GitCredentialCreate,
    GitCredentialOut,
    GitCredentialUpdate,
)
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateGitCredentialError(Exception):
    pass


class GitCredentialNotFoundError(Exception):
    pass


class GitCredentialReferencedError(Exception):
    pass


def _build_secret_path(host: str, key_id: str) -> str:
    """Chemin reel dans Harpocrate : /git/{host}/{key_id}."""
    return f"/git/{host}/{key_id}"


def _build_vault_ref(vault_name: str, host: str, key_id: str) -> str:
    """Reference complete stockee en DB : ${vault://vault_name:/git/host/key_id}."""
    return build_ref(vault_name, _build_secret_path(host, key_id))


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


async def list_git_credentials(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[GitCredentialOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, host, scope_url, harpo_path, created_at "
        "FROM git_credentials WHERE vault_id = $1::uuid "
        "ORDER BY host, key_id",
        vault_id,
    )
    return [GitCredentialOut.model_validate(dict(r)) for r in rows]


async def create_git_credential(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: GitCredentialCreate,
) -> GitCredentialOut:
    secret_path = _build_secret_path(req.host, req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.host, req.key_id)

    # Ecriture dans Harpocrate (chemin sans nom de vault)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, req.value)

    try:
        row = await conn.fetchrow(
            "INSERT INTO git_credentials "
            "(key_id, label, host, scope_url, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4, $5::uuid, $6) "
            "RETURNING id, key_id, label, host, scope_url, harpo_path, created_at",
            req.key_id,
            req.label,
            req.host,
            req.scope_url,
            vault["id"],
            vault_ref,
        )
    except asyncpg.UniqueViolationError as exc:
        # Rollback Harpocrate best-effort (idempotent)
        await asyncio.to_thread(client.delete_secret, secret_path)
        raise DuplicateGitCredentialError(
            f"key_id={req.key_id!r} already exists for host={req.host!r}"
        ) from exc

    log.info(
        "git_credential.created",
        vault_id=vault["id"],
        host=req.host,
        key_id=req.key_id,
    )
    return GitCredentialOut.model_validate(dict(row))


async def update_git_credential(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: GitCredentialUpdate,
) -> GitCredentialOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, host, scope_url, harpo_path, created_at "
        "FROM git_credentials WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return None

    if req.value is not None:
        # harpo_path est un vault_ref -> extraire le chemin reel pour Harpocrate
        _, secret_path = parse_ref(row["harpo_path"])
        client = await _get_vault_client(conn, vault, vault_svc)
        await asyncio.to_thread(client.set_secret, secret_path, req.value)

    new_label = req.label if req.label is not None else row["label"]
    new_scope_url = req.scope_url if req.scope_url is not None else row["scope_url"]
    updated = await conn.fetchrow(
        "UPDATE git_credentials SET label = $1, scope_url = $2 WHERE id = $3::uuid "
        "RETURNING id, key_id, label, host, scope_url, harpo_path, created_at",
        new_label,
        new_scope_url,
        key_id,
    )
    log.info("git_credential.updated", id=key_id)
    return GitCredentialOut.model_validate(dict(updated))


async def delete_git_credential(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM git_credentials "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    # Verification de reference : aucune source ne doit utiliser ce harpo_path
    ref_count = await conn.fetchval(
        "SELECT count(*) FROM sources WHERE config->>'auth_ref' LIKE $1",
        f"%{row['harpo_path']}%",
    )
    if int(ref_count or 0) > 0:
        raise GitCredentialReferencedError(
            f"harpo_path={row['harpo_path']!r} referenced in sources"
        )

    # Suppression Harpocrate (harpo_path = vault_ref -> extraire le chemin reel)
    _, secret_path = parse_ref(row["harpo_path"])
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, secret_path)

    await conn.execute("DELETE FROM git_credentials WHERE id = $1::uuid", key_id)
    log.info("git_credential.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
