from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.user_api_keys import (
    GrantsUpdate,
    UserApiKeyCreate,
    UserApiKeyCreated,
    UserApiKeyOut,
    UserApiKeyRotated,
    WorkspaceGrantIn,
    WorkspaceGrantOut,
)

log = structlog.get_logger(__name__)

_GRACE_HOURS = 72

class UnknownWorkspaceError(ValueError):
    """Un grant référence un workspace inexistant."""


async def _check_workspaces_exist(
    conn: asyncpg.Connection, grants: list[WorkspaceGrantIn]
) -> None:
    if not grants:
        return
    ids = [g.workspace_id for g in grants]
    found = await conn.fetchval(
        "SELECT COUNT(*) FROM workspaces WHERE id = ANY($1::uuid[])", ids
    )
    if found != len(set(ids)):
        raise UnknownWorkspaceError("un ou plusieurs workspaces n'existent pas")


async def _insert_grants(
    conn: asyncpg.Connection, key_id: UUID, grants: list[WorkspaceGrantIn]
) -> None:
    await conn.executemany(
        """
        INSERT INTO user_api_key_workspaces (api_key_id, workspace_id, can_read, can_write)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (api_key_id, workspace_id)
        DO UPDATE SET can_read = EXCLUDED.can_read, can_write = EXCLUDED.can_write
        """,
        [(key_id, g.workspace_id, g.can_read, g.can_write) for g in grants],
    )


async def _grants_for_keys(
    conn: asyncpg.Connection, key_ids: list[UUID]
) -> dict[UUID, list[WorkspaceGrantOut]]:
    rows = await conn.fetch(
        """
        SELECT g.api_key_id, g.workspace_id, g.can_read, g.can_write, w.name
        FROM user_api_key_workspaces g
        JOIN workspaces w ON w.id = g.workspace_id
        WHERE g.api_key_id = ANY($1::uuid[])
        ORDER BY w.name
        """,
        key_ids,
    )
    result: dict[UUID, list[WorkspaceGrantOut]] = {}
    for r in rows:
        result.setdefault(r["api_key_id"], []).append(
            WorkspaceGrantOut(
                workspace_id=r["workspace_id"],
                workspace_name=r["name"],
                can_read=r["can_read"],
                can_write=r["can_write"],
            )
        )
    return result


async def list_for_owner(
    conn: asyncpg.Connection, *, owner_id: str
) -> list[UserApiKeyOut]:
    rows = await conn.fetch(
        """
        SELECT k.id, k.name, k.fingerprint, k.created_at, k.revoked_at, k.rotated_at,
        CASE
            WHEN k.revoked_at IS NOT NULL THEN 'revoked'
            WHEN k.rotated_at IS NOT NULL
                 AND k.rotated_at <= now() - interval '72 hours' THEN 'expired'
            WHEN k.rotated_at IS NOT NULL THEN 'grace_period'
            ELSE 'active'
        END AS status
        FROM user_api_keys k
        WHERE k.owner_id = $1
        ORDER BY k.created_at DESC
        """,
        owner_id,
    )
    grants = await _grants_for_keys(conn, [r["id"] for r in rows])
    return [
        UserApiKeyOut(
            id=r["id"],
            name=r["name"],
            fingerprint_preview=r["fingerprint"][:8],
            status=r["status"],
            created_at=r["created_at"],
            revoked_at=r["revoked_at"],
            rotated_at=r["rotated_at"],
            workspaces=grants.get(r["id"], []),
        )
        for r in rows
    ]


async def create_key(
    conn: asyncpg.Connection, *, owner_id: str, req: UserApiKeyCreate
) -> UserApiKeyCreated:
    from rag.services.apikey import generate_api_key

    api_key = generate_api_key()
    fp = sha256(api_key.encode()).hexdigest()

    async with conn.transaction():
        await _check_workspaces_exist(conn, req.workspaces)
        row = await conn.fetchrow(
            """
            INSERT INTO user_api_keys (owner_id, name, fingerprint)
            VALUES ($1, $2, $3)
            RETURNING id, name, created_at
            """,
            owner_id, req.name, fp,
        )
        await _insert_grants(conn, row["id"], req.workspaces)

    log.info("user_api_key.created", owner_id=owner_id, name=req.name)
    return UserApiKeyCreated(
        id=row["id"],
        name=row["name"],
        api_key=api_key,
        fingerprint_preview=fp[:8],
        created_at=row["created_at"],
    )


async def rotate_key(
    conn: asyncpg.Connection, *, owner_id: str, key_id: str
) -> UserApiKeyRotated | None:
    from rag.services.apikey import generate_api_key

    old = await conn.fetchrow(
        "SELECT id, name, revoked_at FROM user_api_keys "
        "WHERE owner_id = $1 AND id = $2::uuid",
        owner_id, key_id,
    )
    if old is None:
        return None
    if old["revoked_at"] is not None:
        raise ValueError("cannot rotate a revoked key")

    new_api_key = generate_api_key()
    new_fp = sha256(new_api_key.encode()).hexdigest()
    now = datetime.now(UTC)

    async with conn.transaction():
        new_key_id = await conn.fetchval(
            """
            INSERT INTO user_api_keys (owner_id, name, fingerprint)
            VALUES ($1, $2 || ' (rotation)', $3)
            RETURNING id
            """,
            owner_id, old["name"], new_fp,
        )
        # La nouvelle clé hérite des grants de l'ancienne.
        await conn.execute(
            """
            INSERT INTO user_api_key_workspaces (api_key_id, workspace_id, can_read, can_write)
            SELECT $1, workspace_id, can_read, can_write
            FROM user_api_key_workspaces WHERE api_key_id = $2::uuid
            """,
            new_key_id, key_id,
        )
        await conn.execute(
            "UPDATE user_api_keys SET rotated_at = $1 WHERE id = $2::uuid",
            now, key_id,
        )

    log.info("user_api_key.rotated", owner_id=owner_id, old=key_id)
    return UserApiKeyRotated(
        new_key_id=new_key_id,
        new_api_key=new_api_key,
        new_fingerprint_preview=new_fp[:8],
        old_key_id=UUID(key_id),
        grace_until=now + timedelta(hours=_GRACE_HOURS),
    )


async def revoke_key(
    conn: asyncpg.Connection, *, owner_id: str, key_id: str
) -> bool:
    result = await conn.execute(
        "UPDATE user_api_keys SET revoked_at = now() "
        "WHERE owner_id = $1 AND id = $2::uuid AND revoked_at IS NULL",
        owner_id, key_id,
    )
    return result != "UPDATE 0"


async def set_grants(
    conn: asyncpg.Connection, *, owner_id: str, key_id: str, req: GrantsUpdate
) -> bool:
    """Remplace l'ensemble des grants d'une clé (édition des cases cochées)."""
    owned = await conn.fetchval(
        "SELECT 1 FROM user_api_keys WHERE owner_id = $1 AND id = $2::uuid",
        owner_id, key_id,
    )
    if not owned:
        return False
    async with conn.transaction():
        await _check_workspaces_exist(conn, req.workspaces)
        await conn.execute(
            "DELETE FROM user_api_key_workspaces WHERE api_key_id = $1::uuid", key_id
        )
        await _insert_grants(conn, UUID(key_id), req.workspaces)
    log.info("user_api_key.grants_updated", owner_id=owner_id, key=key_id)
    return True
