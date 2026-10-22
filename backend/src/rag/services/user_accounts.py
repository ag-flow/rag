"""Administration des comptes et de leurs rôles (ticket a138f63b).

Le rôle vit en base (STANDARD Authentification OIDC §1, §9 ; migration 099) et
se relit à chaque requête : le changer ici prend effet immédiatement, pour une
session OIDC comme pour une session locale.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

import asyncpg
import structlog
from pydantic import BaseModel

log = structlog.get_logger(__name__)

ADMIN_ROLE = "rag-admin"

_LIST_USERS = (
    "SELECT id, username, email, role, oidc_issuer, password_hash <> '' AS has_local_password, "
    "created_at FROM users ORDER BY created_at, username"
)
# Les admins sont verrouillés le temps du changement : deux rétrogradations
# simultanées ne peuvent pas, chacune croyant en laisser un, n'en laisser aucun.
_LOCK_ADMINS = "SELECT id FROM users WHERE role = 'rag-admin' FOR UPDATE"
_SELECT_ROLE_FOR_UPDATE = "SELECT role FROM users WHERE id = $1 FOR UPDATE"
_UPDATE_ROLE = "UPDATE users SET role = $2 WHERE id = $1"


class UserAccount(BaseModel):
    id: UUID
    username: str
    email: str
    role: str | None
    # Émetteur OIDC du compte ancré ; None = jamais connecté en OIDC.
    oidc_issuer: str | None
    has_local_password: bool
    created_at: datetime


class UserNotFoundError(Exception):
    pass


class LastAdminError(Exception):
    """Retirer rag-admin au dernier administrateur verrouillerait l'instance."""


async def db_list_users(conn: asyncpg.Connection) -> list[UserAccount]:
    rows = await conn.fetch(_LIST_USERS)
    return [UserAccount.model_validate(dict(r)) for r in rows]


async def db_set_role(
    conn: asyncpg.Connection, *, user_id: UUID, role: str | None, actor_owner_id: str
) -> UserAccount:
    """Change le rôle d'un compte ; refuse de laisser l'instance sans admin."""
    async with conn.transaction():
        admins = {r["id"] for r in await conn.fetch(_LOCK_ADMINS)}
        current = await conn.fetchrow(_SELECT_ROLE_FOR_UPDATE, user_id)
        if current is None:
            raise UserNotFoundError(str(user_id))
        if role != ADMIN_ROLE and user_id in admins and len(admins) == 1:
            raise LastAdminError(str(user_id))
        await conn.execute(_UPDATE_ROLE, user_id, role)
    log.info(
        "user_accounts.role_changed",
        user_id=str(user_id),
        old_role=current["role"],
        new_role=role,
        actor=actor_owner_id[:12],
    )
    updated = next(u for u in await db_list_users(conn) if u.id == user_id)
    return updated


async def db_role_for_username(pool: asyncpg.Pool, username: str) -> str | None:
    """Rôle en base d'un compte local — relu à chaque requête."""
    role: str | None = await pool.fetchval("SELECT role FROM users WHERE username = $1", username)
    return role
