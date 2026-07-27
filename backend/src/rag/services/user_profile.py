from __future__ import annotations

import re
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)

# GUID libre mais borné : le portail génère des UUID, la saisie libre est
# tolérée (opaque par contrat) — on refuse juste le vide et l'espace.
_IDENTITY_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{7,127}$")


class IdentityTakenError(Exception):
    """Le GUID d'identité est déjà utilisé par un autre utilisateur."""


class EmailTakenError(Exception):
    """L'email est déjà utilisé par un autre utilisateur."""


class InvalidIdentityError(Exception):
    """Format de GUID d'identité invalide."""


async def get_or_create_user(
    conn: asyncpg.Connection, *, email: str, username: str | None = None
) -> dict[str, Any]:
    """Retourne la ligne user pour cet email, en la créant si besoin.

    Auto-provisionnement OIDC : au premier accès d'un utilisateur OIDC, aucune
    ligne n'existe (la table venait de l'auth locale) — on la crée sans mot de
    passe local (password_hash vide = login local impossible).
    """
    row = await conn.fetchrow(
        "SELECT id, username, email, identity FROM users WHERE email = $1", email
    )
    if row is not None:
        return dict(row)
    created = await conn.fetchrow(
        """
        INSERT INTO users (username, email, password_hash)
        VALUES ($1, $2, '')
        ON CONFLICT (email) DO UPDATE SET email = EXCLUDED.email
        RETURNING id, username, email, identity
        """,
        username or email,
        email,
    )
    log.info("user_profile.provisioned", email=email)
    return dict(created)


async def update_profile(
    conn: asyncpg.Connection,
    *,
    current_email: str,
    new_email: str | None = None,
    identity: str | None = None,
) -> dict[str, Any]:
    """Met à jour email et/ou GUID d'identité du user courant.

    - identity : None = inchangé, "" = effacement, sinon validé (_IDENTITY_RE)
      et unique (IdentityTakenError).
    - new_email : unique (EmailTakenError). ⚠️ changer d'email change le
      owner_id dérivé — l'appelant (IHM) l'annonce à l'utilisateur.
    """
    user = await get_or_create_user(conn, email=current_email)

    if identity is not None and identity != "":
        if not _IDENTITY_RE.match(identity):
            raise InvalidIdentityError(identity)
        holder = await conn.fetchval(
            "SELECT email FROM users WHERE identity = $1 AND email <> $2",
            identity,
            current_email,
        )
        if holder is not None:
            raise IdentityTakenError(identity)

    if new_email is not None and new_email != current_email:
        taken = await conn.fetchval(
            "SELECT 1 FROM users WHERE email = $1 AND id <> $2", new_email, user["id"]
        )
        if taken is not None:
            raise EmailTakenError(new_email)

    row = await conn.fetchrow(
        """
        UPDATE users
        SET email = COALESCE($2, email),
            identity = CASE WHEN $3::text IS NULL THEN identity
                            WHEN $3 = '' THEN NULL
                            ELSE $3 END
        WHERE id = $1
        RETURNING id, username, email, identity
        """,
        user["id"],
        new_email,
        identity,
    )
    return dict(row)


async def email_for_identity(pool: asyncpg.Pool, identity: str) -> str | None:
    """Email du user dont le GUID d'identité correspond — mapping OBO (v6).

    None si aucun user ne porte ce GUID : l'appel reste attribué à la clé
    (fail-safe du contrat, jamais d'erreur).
    """
    return await pool.fetchval("SELECT email FROM users WHERE identity = $1", identity)
