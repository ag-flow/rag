"""Résolution d'un login OIDC vers un compte local (ticket 730cb2d6).

STANDARD Authentification OIDC : l'identité d'un compte fédéré est le couple
(issuer, sub), épinglé au premier login ; l'email vérifié n'est qu'un PONT
d'amorce pour retrouver un compte pas encore ancré (§3, §4) ; les rôles vivent
en base, le token ne fait que suggérer celui d'un nouvel arrivant (§1, §9).

Ordre de résolution :
1. (issuer, sub) déjà épinglé → ce compte, quoi que dise l'email ;
2. sinon pont par email, seulement si l'email est présent ET vérifié :
   - compte jamais ancré → on l'ancre ;
   - compte ancré chez le MÊME émetteur avec un autre sub → refus, toujours ;
   - compte ancré chez un AUTRE émetteur → re-liaison si la fenêtre est
     ouverte, refus sinon ;
3. aucun compte → provisioning d'un nouveau compte.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg
import structlog

log = structlog.get_logger(__name__)

_ROLES = ("rag-admin", "rag-viewer")
# Requêtes littérales (aucune interpolation) ; colonnes rendues partout :
# id, username, email, owner_id, role, oidc_issuer, oidc_sub.
_SELECT_BY_ANCHOR = (
    "SELECT id, username, email, owner_id, role, oidc_issuer, oidc_sub FROM users "
    "WHERE oidc_issuer = $1 AND oidc_sub = $2 FOR UPDATE"
)
_SELECT_BY_EMAIL = (
    "SELECT id, username, email, owner_id, role, oidc_issuer, oidc_sub FROM users "
    "WHERE lower(email) = lower($1) FOR UPDATE"
)
_UPDATE_EMAIL = (
    "UPDATE users SET email = $2 WHERE id = $1 "
    "RETURNING id, username, email, owner_id, role, oidc_issuer, oidc_sub"
)
_UPDATE_ANCHOR = (
    "UPDATE users SET oidc_issuer = $2, oidc_sub = $3 WHERE id = $1 "
    "RETURNING id, username, email, owner_id, role, oidc_issuer, oidc_sub"
)
_UPDATE_ROLE = (
    "UPDATE users SET role = $2 WHERE id = $1 "
    "RETURNING id, username, email, owner_id, role, oidc_issuer, oidc_sub"
)
_INSERT_USER = (
    "INSERT INTO users (username, email, password_hash, role, oidc_issuer, oidc_sub) "
    "VALUES ($1, $2, '', $3, $4, $5) "
    "RETURNING id, username, email, owner_id, role, oidc_issuer, oidc_sub"
)
_INSERT_HISTORY = (
    "INSERT INTO user_oidc_identity_history (user_id, oidc_issuer, oidc_sub) VALUES ($1, $2, $3)"
)


@dataclass(frozen=True)
class OidcLogin:
    """Ce que le login apporte, extrait d'un id_token DÉJÀ vérifié."""

    issuer: str
    sub: str
    email: str | None
    email_verified: bool
    username: str | None
    # Rôles lus dans le token : simple suggestion pour un compte sans rôle.
    token_roles: tuple[str, ...]


@dataclass(frozen=True)
class ResolvedUser:
    user_id: str
    owner_id: str
    email: str
    role: str | None


class OidcIdentityRefusedError(Exception):
    """Login authentifié par l'IdP mais refusé par la liaison d'identité.

    `reason` est un code stable, sûr à renvoyer au navigateur.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def suggested_role(token_roles: tuple[str, ...]) -> str | None:
    """Rôle à proposer à un compte qui n'en a pas encore — jamais à l'exécution."""
    for role in _ROLES:
        if role in token_roles:
            return role
    return None


async def resolve_oidc_user(
    conn: asyncpg.Connection, login: OidcLogin, *, relink_enabled: bool
) -> ResolvedUser:
    """Retrouve, ancre ou crée le compte local d'un login OIDC.

    Une seule transaction, lignes candidates verrouillées : deux logins
    simultanés du même humain ne peuvent ni dupliquer le compte ni épingler
    deux sub différents.
    """
    async with conn.transaction():
        anchored = await conn.fetchrow(_SELECT_BY_ANCHOR, login.issuer, login.sub)
        if anchored is not None:
            row = await _refresh_known_user(conn, anchored, login)
        else:
            row = await _bridge_or_provision(conn, login, relink_enabled=relink_enabled)
    return ResolvedUser(
        user_id=str(row["id"]), owner_id=row["owner_id"], email=row["email"], role=row["role"]
    )


async def _refresh_known_user(
    conn: asyncpg.Connection, row: asyncpg.Record, login: OidcLogin
) -> asyncpg.Record:
    """Compte retrouvé par son ancrage : l'email a pu changer côté IdP.

    L'owner_id ne bouge pas (il est figé) : un changement d'email ne crée ni
    doublon ni objets orphelins. On reporte l'email vérifié s'il est libre ;
    sinon on garde l'ancien plutôt que de voler l'adresse d'un autre compte.
    """
    updated = row
    new_email = login.email
    if login.email_verified and new_email and new_email.lower() != row["email"].lower():
        taken = await conn.fetchval(
            "SELECT 1 FROM users WHERE lower(email) = lower($1) AND id <> $2",
            new_email,
            row["id"],
        )
        if taken:
            log.warning("oidc_identity.email_change_skipped", user_id=str(row["id"]))
        else:
            updated = await conn.fetchrow(_UPDATE_EMAIL, row["id"], new_email)
            log.info("oidc_identity.email_updated", user_id=str(row["id"]))
    return await _ensure_role(conn, updated, login)


async def _bridge_or_provision(
    conn: asyncpg.Connection, login: OidcLogin, *, relink_enabled: bool
) -> asyncpg.Record:
    if not login.email:
        # users.email est obligatoire et sert de pont : sans lui, ni
        # rapprochement possible ni compte créable proprement.
        raise OidcIdentityRefusedError("email_missing")
    candidates = await conn.fetch(_SELECT_BY_EMAIL, login.email)
    if len(candidates) > 1:
        # §4 : on ne choisit jamais au hasard, l'admin tranche.
        raise OidcIdentityRefusedError("email_ambiguous")
    if not candidates:
        return await _provision(conn, login)
    if not login.email_verified:
        # §4 fail closed : un email non vérifié permettrait d'endosser le
        # compte existant qui porte cette adresse.
        raise OidcIdentityRefusedError("email_unverified")
    candidate = candidates[0]
    if candidate["oidc_issuer"] is None:
        return await _ensure_role(conn, await _pin(conn, candidate, login), login)
    if candidate["oidc_issuer"] == login.issuer:
        # Discriminant = l'ÉMETTEUR, jamais le mode : même émetteur et autre
        # sub, c'est un autre sujet qui porte la même adresse. Refus même
        # fenêtre de re-liaison ouverte — sinon la fenêtre de migration
        # devient une fenêtre de prise de contrôle de compte.
        log.warning("oidc_identity.sub_mismatch_refused", user_id=str(candidate["id"]))
        raise OidcIdentityRefusedError("sub_mismatch")
    if not relink_enabled:
        log.warning("oidc_identity.relink_closed", user_id=str(candidate["id"]))
        raise OidcIdentityRefusedError("relink_closed")
    await conn.execute(
        "UPDATE user_oidc_identity_history SET replaced_at = now() "
        "WHERE user_id = $1 AND replaced_at IS NULL",
        candidate["id"],
    )
    log.info("oidc_identity.relinked", user_id=str(candidate["id"]))
    return await _ensure_role(conn, await _pin(conn, candidate, login), login)


async def _pin(conn: asyncpg.Connection, row: asyncpg.Record, login: OidcLogin) -> asyncpg.Record:
    pinned = await conn.fetchrow(_UPDATE_ANCHOR, row["id"], login.issuer, login.sub)
    await conn.execute(_INSERT_HISTORY, row["id"], login.issuer, login.sub)
    log.info("oidc_identity.pinned", user_id=str(row["id"]))
    return pinned


async def _provision(conn: asyncpg.Connection, login: OidcLogin) -> asyncpg.Record:
    """Nouvel arrivant : compte créé, ancré, rôle suggéré par le token (§9)."""
    username = login.username or login.email
    taken = await conn.fetchval("SELECT 1 FROM users WHERE username = $1", username)
    if taken:
        # Login d'un autre compte : l'email (unique) devient le nom de compte.
        username = login.email
    # owner_id posé par le trigger de la migration 099 : un seul point de calcul.
    row = await conn.fetchrow(
        _INSERT_USER,
        username,
        login.email,
        suggested_role(login.token_roles),
        login.issuer,
        login.sub,
    )
    await conn.execute(_INSERT_HISTORY, row["id"], login.issuer, login.sub)
    log.info("oidc_identity.provisioned", user_id=str(row["id"]), role=row["role"])
    return row


async def _ensure_role(
    conn: asyncpg.Connection, row: asyncpg.Record, login: OidcLogin
) -> asyncpg.Record:
    """Compte sans rôle (créé avant ce lot) : la suggestion du token l'amorce,
    une seule fois. Un rôle déjà en base n'est JAMAIS écrasé par le token."""
    if row["role"] is not None:
        return row
    role = suggested_role(login.token_roles)
    if role is None:
        return row
    updated = await conn.fetchrow(_UPDATE_ROLE, row["id"], role)
    log.info("oidc_identity.role_seeded", user_id=str(row["id"]), role=role)
    return updated


async def db_role_for_user(pool: asyncpg.Pool, user_id: str) -> str | None:
    """Rôle courant en base — relu à chaque requête : une rétrogradation
    s'applique immédiatement, sans attendre l'expiration du token."""
    role: Any = await pool.fetchval("SELECT role FROM users WHERE id = $1::uuid", user_id)
    return role if isinstance(role, str) else None
