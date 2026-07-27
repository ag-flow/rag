from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
from uuid import UUID

import asyncpg
import structlog

from rag.schemas.user_api_keys import (
    ScopeUpdate,
    UserApiKeyCreate,
    UserApiKeyCreated,
    UserApiKeyOut,
    UserApiKeyRotated,
)

log = structlog.get_logger(__name__)

_GRACE_HOURS = 72


async def list_for_owner(conn: asyncpg.Connection, *, owner_id: str) -> list[UserApiKeyOut]:
    rows = await conn.fetch(
        """
        SELECT k.id, k.name, k.fingerprint, k.scope, k.created_at,
               k.revoked_at, k.rotated_at,
               CASE
                   WHEN k.revoked_at IS NOT NULL THEN 'revoked'
                   WHEN k.rotated_at IS NOT NULL
                        AND k.rotated_at <= now() - interval '72 hours' THEN 'expired'
                   WHEN k.rotated_at IS NOT NULL THEN 'grace_period'
                   ELSE 'active'
               END AS status
        FROM user_api_keys k
        WHERE k.owner_id = $1
          -- Une clé révoquée reste visible 24h (traçabilité) puis disparaît de
          -- la liste ; la ligne reste en base pour l'audit.
          AND (k.revoked_at IS NULL OR k.revoked_at > now() - interval '24 hours')
        ORDER BY k.created_at DESC
        """,
        owner_id,
    )
    return [
        UserApiKeyOut(
            id=r["id"],
            name=r["name"],
            fingerprint_preview=r["fingerprint"][:8],
            status=r["status"],
            scope=r["scope"],
            created_at=r["created_at"],
            revoked_at=r["revoked_at"],
            rotated_at=r["rotated_at"],
        )
        for r in rows
    ]


async def create_key(
    conn: asyncpg.Connection, *, owner_id: str, req: UserApiKeyCreate
) -> UserApiKeyCreated:
    from rag.services.apikey import generate_api_key

    api_key = generate_api_key()
    fp = sha256(api_key.encode()).hexdigest()

    row = await conn.fetchrow(
        """
        INSERT INTO user_api_keys (owner_id, name, fingerprint, scope)
        VALUES ($1, $2, $3, $4)
        RETURNING id, name, scope, created_at
        """,
        owner_id,
        req.name,
        fp,
        req.scope,
    )

    log.info("user_api_key.created", owner_id=owner_id, name=req.name, scope=req.scope)
    return UserApiKeyCreated(
        id=row["id"],
        name=row["name"],
        api_key=api_key,
        fingerprint_preview=fp[:8],
        scope=row["scope"],
        created_at=row["created_at"],
    )


async def rotate_key(
    conn: asyncpg.Connection, *, owner_id: str, key_id: str
) -> UserApiKeyRotated | None:
    from rag.services.apikey import generate_api_key

    old = await conn.fetchrow(
        "SELECT id, name, scope, revoked_at FROM user_api_keys "
        "WHERE owner_id = $1 AND id = $2::uuid",
        owner_id,
        key_id,
    )
    if old is None:
        return None
    if old["revoked_at"] is not None:
        raise ValueError("cannot rotate a revoked key")

    new_api_key = generate_api_key()
    new_fp = sha256(new_api_key.encode()).hexdigest()
    now = datetime.now(UTC)

    async with conn.transaction():
        # La nouvelle clé hérite du niveau d'accès de l'ancienne.
        new_key_id = await conn.fetchval(
            """
            INSERT INTO user_api_keys (owner_id, name, fingerprint, scope)
            VALUES ($1, $2 || ' (rotation)', $3, $4)
            RETURNING id
            """,
            owner_id,
            old["name"],
            new_fp,
            old["scope"],
        )
        await conn.execute(
            "UPDATE user_api_keys SET rotated_at = $1 WHERE id = $2::uuid",
            now,
            key_id,
        )

    log.info("user_api_key.rotated", owner_id=owner_id, old=key_id)
    return UserApiKeyRotated(
        new_key_id=new_key_id,
        new_api_key=new_api_key,
        new_fingerprint_preview=new_fp[:8],
        old_key_id=UUID(key_id),
        grace_until=now + timedelta(hours=_GRACE_HOURS),
    )


async def revoke_key(conn: asyncpg.Connection, *, owner_id: str, key_id: str) -> bool:
    result = await conn.execute(
        "UPDATE user_api_keys SET revoked_at = now() "
        "WHERE owner_id = $1 AND id = $2::uuid AND revoked_at IS NULL",
        owner_id,
        key_id,
    )
    return result != "UPDATE 0"


async def set_scope(
    conn: asyncpg.Connection, *, owner_id: str, key_id: str, req: ScopeUpdate
) -> bool:
    """Change le niveau d'accès d'une clé active."""
    result = await conn.execute(
        "UPDATE user_api_keys SET scope = $3 "
        "WHERE owner_id = $1 AND id = $2::uuid AND revoked_at IS NULL",
        owner_id,
        key_id,
        req.scope,
    )
    if result != "UPDATE 0":
        log.info("user_api_key.scope_updated", owner_id=owner_id, key=key_id, scope=req.scope)
        return True
    return False
