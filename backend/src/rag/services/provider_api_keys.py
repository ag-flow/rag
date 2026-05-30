from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.provider_api_keys import (
    ProviderApiKeyCreate,
    ProviderApiKeyOut,
    ProviderApiKeyUpdate,
)
from rag.secrets.refs import build_ref, parse_ref
from rag.secrets.vault import HarpocrateVaultClient

log = structlog.get_logger(__name__)


class DuplicateProviderKeyError(Exception):
    pass


class ProviderKeyNotFoundError(Exception):
    pass


class ProviderKeyReferencedError(Exception):
    pass


def _build_secret_path(provider: str, key_id: str) -> str:
    """Chemin réel dans Harpocrate : /{provider}/{key_id}."""
    return f"/{provider}/{key_id}"


def _build_vault_ref(vault_name: str, provider: str, key_id: str) -> str:
    """Référence complète stockée en DB : ${vault://vault_name:/provider/key_id}."""
    return build_ref(vault_name, _build_secret_path(provider, key_id))


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
        "SELECT id, key_id, label, provider, harpo_path, expires_at, created_at "
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
    secret_path = _build_secret_path(req.provider, req.key_id)
    vault_ref = _build_vault_ref(vault["name"], req.provider, req.key_id)

    expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else None
    )

    # Ecriture dans Harpocrate (chemin sans nom de vault)
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.set_secret, secret_path, req.value)

    try:
        row = await conn.fetchrow(
            "INSERT INTO provider_api_keys "
            "(key_id, label, provider, vault_id, harpo_path, expires_at) "
            "VALUES ($1, $2, $3, $4::uuid, $5, $6) "
            "RETURNING id, key_id, label, provider, harpo_path, expires_at, created_at",
            req.key_id,
            req.label,
            req.provider,
            vault["id"],
            vault_ref,
            expires_at,
        )
    except asyncpg.UniqueViolationError as exc:
        # Rollback Harpocrate best-effort (idempotent)
        await asyncio.to_thread(client.delete_secret, secret_path)
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
        "SELECT id, key_id, label, provider, harpo_path, expires_at, created_at "
        "FROM provider_api_keys WHERE id = $1::uuid AND vault_id = $2::uuid",
        key_id,
        vault["id"],
    )
    if row is None:
        return None

    if req.value is not None:
        _, secret_path = parse_ref(row["harpo_path"])
        client = await _get_vault_client(conn, vault, vault_svc)
        await asyncio.to_thread(client.set_secret, secret_path, req.value)

    new_label = req.label if req.label is not None else row["label"]
    new_expires_at = (
        datetime.now(UTC) + timedelta(days=req.valid_days)
        if req.valid_days is not None
        else row["expires_at"]
    )
    updated = await conn.fetchrow(
        "UPDATE provider_api_keys SET label = $1, expires_at = $2 WHERE id = $3::uuid "
        "RETURNING id, key_id, label, provider, harpo_path, expires_at, created_at",
        new_label,
        new_expires_at,
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

    # Suppression Harpocrate (harpo_path = vault_ref → extraire le chemin réel)
    _, secret_path = parse_ref(row["harpo_path"])
    client = await _get_vault_client(conn, vault, vault_svc)
    await asyncio.to_thread(client.delete_secret, secret_path)

    await conn.execute("DELETE FROM provider_api_keys WHERE id = $1::uuid", key_id)
    log.info("provider_key.deleted", id=key_id, harpo_path=row["harpo_path"])
    return True


async def list_provider_keys_by_provider(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
    provider: str,
) -> list[dict]:
    """Retourne les clés pour `provider` des vaults accessibles à `owner_id`.

    Vaults éligibles : is_default = true OU owner_id = $owner_id.
    """
    rows = await conn.fetch(
        "SELECT pk.id, pk.key_id, pk.label, pk.provider, pk.harpo_path, "
        "pk.created_at, v.name AS vault_name, v.label AS vault_label "
        "FROM provider_api_keys pk "
        "JOIN harpocrate_vaults v ON v.id = pk.vault_id "
        "WHERE pk.provider = $1 "
        "AND (v.is_default = true OR v.owner_id = $2) "
        "ORDER BY v.name, pk.key_id",
        provider,
        owner_id,
    )
    return [dict(r) for r in rows]
