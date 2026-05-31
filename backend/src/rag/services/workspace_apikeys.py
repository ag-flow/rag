from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from typing import Any
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.workspace_apikeys import (
    ApiKeyCreate,
    ApiKeyCreated,
    ApiKeyOut,
    ApiKeyRotated,
)
from rag.secrets.refs import build_ref

log = structlog.get_logger(__name__)

_GRACE_HOURS = 72


def _key_path(workspace_name: str, key_id: str) -> str:
    return f"wsapi_{workspace_name}/{key_id}"


async def _get_vault_and_client(
    vault_svc: Any,
    client_provider: Any,
    config_pool: asyncpg.Pool,
) -> tuple[Any, Any]:
    async with config_pool.acquire() as conn:
        vault = await vault_svc.get_default(conn)
    if vault is None:
        raise RuntimeError("no default Harpocrate vault configured")
    client = await client_provider.get_client(vault.api_key_id)
    return vault, client


async def list_keys(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
) -> list[ApiKeyOut]:
    rows = await conn.fetch(
        """
        SELECT k.id, k.name, k.fingerprint, k.api_key_ref,
               k.created_at, k.revoked_at, k.rotated_at,
               CASE
                   WHEN k.revoked_at IS NOT NULL THEN 'revoked'
                   WHEN k.rotated_at IS NOT NULL
                        AND k.rotated_at <= now() - interval '72 hours' THEN 'expired'
                   WHEN k.rotated_at IS NOT NULL THEN 'grace_period'
                   ELSE 'active'
               END AS status
        FROM workspace_api_keys k
        JOIN workspaces w ON w.id = k.workspace_id
        WHERE w.name = $1
        ORDER BY k.created_at DESC
        """,
        workspace_name,
    )
    return [
        ApiKeyOut(
            id=r["id"],
            name=r["name"],
            fingerprint_preview=r["fingerprint"][:8],
            api_key_ref=r["api_key_ref"],
            status=r["status"],
            created_at=r["created_at"],
            revoked_at=r["revoked_at"],
            rotated_at=r["rotated_at"],
        )
        for r in rows
    ]


async def create_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    req: ApiKeyCreate,
    vault_svc: Any,
    client_provider: Any,
    config_pool: asyncpg.Pool,
) -> ApiKeyCreated:
    from rag.services.apikey import generate_api_key

    ws_id = await conn.fetchval(
        "SELECT id FROM workspaces WHERE name = $1", workspace_name
    )
    if ws_id is None:
        raise ValueError(f"workspace {workspace_name!r} not found")

    api_key = generate_api_key()
    fp = sha256(api_key.encode()).hexdigest()

    key_id = await conn.fetchval(
        """
        INSERT INTO workspace_api_keys (workspace_id, name, fingerprint, api_key_ref)
        VALUES ($1, $2, $3, 'pending')
        RETURNING id
        """,
        ws_id, req.name, fp,
    )

    vault, client = await _get_vault_and_client(vault_svc, client_provider, config_pool)
    path = _key_path(workspace_name, str(key_id))
    api_key_ref = build_ref(vault.api_key_id, path)

    await asyncio.to_thread(client.set_secret, path, api_key)

    row = await conn.fetchrow(
        """
        UPDATE workspace_api_keys SET api_key_ref = $1
        WHERE id = $2
        RETURNING id, name, fingerprint, created_at
        """,
        api_key_ref, key_id,
    )

    log.info("workspace_api_key.created", workspace=workspace_name, name=req.name)
    return ApiKeyCreated(
        id=row["id"],
        name=row["name"],
        fingerprint_preview=row["fingerprint"][:8],
        api_key=api_key,
        created_at=row["created_at"],
    )


async def rotate_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    key_id: str,
    vault_svc: Any,
    client_provider: Any,
    config_pool: asyncpg.Pool,
) -> ApiKeyRotated | None:
    from rag.services.apikey import generate_api_key

    old_row = await conn.fetchrow(
        """
        SELECT k.id, k.name, k.revoked_at
        FROM workspace_api_keys k
        JOIN workspaces w ON w.id = k.workspace_id
        WHERE w.name = $1 AND k.id = $2::uuid
        """,
        workspace_name, key_id,
    )
    if old_row is None:
        return None
    if old_row["revoked_at"] is not None:
        raise ValueError("cannot rotate a revoked key")

    new_api_key = generate_api_key()
    new_fp = sha256(new_api_key.encode()).hexdigest()

    new_key_id = await conn.fetchval(
        """
        INSERT INTO workspace_api_keys (workspace_id, name, fingerprint, api_key_ref)
        SELECT workspace_id, name || ' (rotation)', $2, 'pending'
        FROM workspace_api_keys WHERE id = $1::uuid
        RETURNING id
        """,
        key_id, new_fp,
    )

    vault, client = await _get_vault_and_client(vault_svc, client_provider, config_pool)
    path = _key_path(workspace_name, str(new_key_id))
    new_api_key_ref = build_ref(vault.api_key_id, path)

    await asyncio.to_thread(client.set_secret, path, new_api_key)

    now = datetime.now(UTC)
    await conn.execute(
        "UPDATE workspace_api_keys SET api_key_ref = $1 WHERE id = $2",
        new_api_key_ref, new_key_id,
    )
    await conn.execute(
        "UPDATE workspace_api_keys SET rotated_at = $1 WHERE id = $2::uuid",
        now, key_id,
    )

    log.info("workspace_api_key.rotated", workspace=workspace_name, old=key_id)
    return ApiKeyRotated(
        new_key_id=new_key_id,
        new_api_key=new_api_key,
        new_fingerprint_preview=new_fp[:8],
        old_key_id=UUID(key_id),
        grace_until=now + timedelta(hours=_GRACE_HOURS),
    )


async def revoke_key(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    key_id: str,
) -> bool:
    result = await conn.execute(
        """
        UPDATE workspace_api_keys k SET revoked_at = now()
        FROM workspaces w
        WHERE w.id = k.workspace_id AND w.name = $1 AND k.id = $2::uuid
          AND k.revoked_at IS NULL
        """,
        workspace_name, key_id,
    )
    return result != "UPDATE 0"
