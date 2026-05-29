from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.provider_api_keys import (
    ProviderApiKeyCreate,
    ProviderApiKeyOut,
    ProviderApiKeyUpdate,
)
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateProviderKeyError(Exception):
    pass


class ProviderKeyNotFoundError(Exception):
    pass


class ProviderKeyReferencedError(Exception):
    pass


def _build_harpo_path(vault_name: str, provider: str, key_id: str) -> str:
    return f"/{vault_name}/{provider}/{key_id}"


async def _get_vault_client(
    conn: asyncpg.Connection,
    vault: dict[str, Any],
    vault_svc: Any,
) -> HarpocrateVaultClient:
    api_key = await vault_svc.reveal_api_key(conn, UUID(vault["id"]))
    if api_key is None:
        raise RuntimeError("Cannot decrypt vault API key — DEK manquant ?")
    return HarpocrateVaultClient(url=vault["base_url"], token=api_key)


async def list_provider_keys(
    conn: asyncpg.Connection,
    *,
    vault_id: str,
) -> list[ProviderApiKeyOut]:
    rows = await conn.fetch(
        "SELECT id, key_id, label, provider, harpo_path, created_at "
        "FROM provider_api_keys WHERE vault_id = $1::uuid "
        "ORDER BY provider, key_id",
        vault_id,
    )
    return [ProviderApiKeyOut.model_validate(dict(r)) for r in rows]


async def create_provider_key(
    conn: asyncpg.Connection,
    *,
    vault: dict[str, Any],
    vault_svc: Any,
    req: ProviderApiKeyCreate,
) -> ProviderApiKeyOut:
    harpo_path = _build_harpo_path(vault["name"], req.provider, req.key_id)

    # Ecriture dans Harpocrate (SDK sync -> thread)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, harpo_path, req.value)

    try:
        row = await conn.fetchrow(
            "INSERT INTO provider_api_keys (key_id, label, provider, vault_id, harpo_path) "
            "VALUES ($1, $2, $3, $4::uuid, $5) "
            "RETURNING id, key_id, label, provider, harpo_path, created_at",
            req.key_id,
            req.label,
            req.provider,
            vault["id"],
            harpo_path,
        )
    except asyncpg.UniqueViolationError as exc:
        # Rollback Harpocrate best-effort (idempotent)
        await asyncio.to_thread(client.delete_secret, harpo_path)
        raise DuplicateProviderKeyError(
            f"key_id={req.key_id!r} already exists for provider={req.provider!r}"
        ) from exc

    log.info(
        "provider_key.created",
        vault_id=vault["id"],
        provider=req.provider,
        key_id=req.key_id,
    )
    return ProviderApiKeyOut.model_validate(dict(row))


async def update_provider_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
    req: ProviderApiKeyUpdate,
) -> ProviderApiKeyOut | None:
    row = await conn.fetchrow(
        "SELECT id, key_id, label, provider, harpo_path, created_at "
        "FROM provider_api_keys WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return None

    if req.value is not None:
        client = await _get_vault_client(conn, vault, vault_svc)
        await asyncio.to_thread(client.set_secret, row["harpo_path"], req.value)

    new_label = req.label if req.label is not None else row["label"]
    updated = await conn.fetchrow(
        "UPDATE provider_api_keys SET label = $1 WHERE id = $2::uuid "
        "RETURNING id, key_id, label, provider, harpo_path, created_at",
        new_label,
        key_id,
    )
    log.info("provider_key.updated", id=key_id)
    return ProviderApiKeyOut.model_validate(dict(updated))


async def delete_provider_key(
    conn: asyncpg.Connection,
    *,
    key_id: str,
    vault: dict[str, Any],
    vault_svc: Any,
) -> bool:
    row = await conn.fetchrow(
        "SELECT id, harpo_path FROM provider_api_keys "
        "WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return False

    # Verification de reference : aucun workspace ne doit utiliser ce harpo_path
    ref_count = await conn.fetchval(
        "SELECT count(*) FROM workspaces WHERE api_key_ref LIKE $1",
        f"%{row['harpo_path']}%",
    )
    if int(ref_count or 0) > 0:
        raise ProviderKeyReferencedError(
            f"harpo_path={row['harpo_path']!r} referenced in workspaces"
        )

    # Suppression Harpocrate (best-effort)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, row["harpo_path"])

    await conn.execute("DELETE FROM provider_api_keys WHERE id = $1::uuid", key_id)
    log.info("provider_key.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True
