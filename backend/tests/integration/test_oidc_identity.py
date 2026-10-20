"""Ancrage de l'identité OIDC sur (issuer, sub) — ticket 730cb2d6.

Critères d'acceptation du ticket, sur base réelle :
- un changement d'email côté IdP ne crée plus de compte en double ;
- émetteur B, même email vérifié, re-liaison ouverte : on retrouve le compte ;
- même émetteur, sub différent : refusé, Y COMPRIS re-liaison ouverte ;
- (le rôle à l'exécution vient de la base : tests de oidc_dependency).
"""

from __future__ import annotations

import hashlib
import shutil
from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.services.oidc_identity import (
    OidcIdentityRefusedError,
    OidcLogin,
    resolve_oidc_user,
)

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
ISSUER_A = "https://idp-a.example/realms/yoops"
ISSUER_B = "https://idp-b.example/realms/yoops"
EMAIL = "gael@example.com"


def _owner(email: str) -> str:
    return hashlib.sha256(email.lower().encode()).hexdigest()


def _login(**over: object) -> OidcLogin:
    data: dict[str, object] = {
        "issuer": ISSUER_A,
        "sub": "sub-a-1",
        "email": EMAIL,
        "email_verified": True,
        "username": "gael",
        "token_roles": ("rag-viewer",),
    }
    data.update(over)
    return OidcLogin(**data)  # type: ignore[arg-type]


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    return session_pool


async def _local_admin(conn: asyncpg.Connection) -> None:
    await conn.execute(
        "INSERT INTO users (username, email, password_hash, role) "
        "VALUES ('admin', $1, 'bcrypt-hash', 'rag-admin')",
        EMAIL,
    )


async def _user_count(conn: asyncpg.Connection) -> int:
    count: int = await conn.fetchval("SELECT count(*) FROM users")
    return count


async def test_first_login_provisions_anchored_user_with_suggested_role(pool) -> None:
    async with pool.acquire() as conn:
        user = await resolve_oidc_user(conn, _login(), relink_enabled=False)
        row = await conn.fetchrow("SELECT oidc_issuer, oidc_sub FROM users")
    assert user.owner_id == _owner(EMAIL)
    assert user.role == "rag-viewer"
    assert (row["oidc_issuer"], row["oidc_sub"]) == (ISSUER_A, "sub-a-1")


async def test_local_admin_bridged_by_verified_email_keeps_admin_role(pool) -> None:
    """§4 : l'admin de bootstrap revenant en OIDC garde son rôle et ses objets."""
    async with pool.acquire() as conn:
        await _local_admin(conn)
        user = await resolve_oidc_user(conn, _login(), relink_enabled=False)
        assert await _user_count(conn) == 1
    assert (user.role, user.owner_id) == ("rag-admin", _owner(EMAIL))


async def test_email_change_at_idp_finds_same_account_and_keeps_owner(pool) -> None:
    """Critère 1 : changement d'email côté IdP → ni doublon, ni objets orphelins."""
    async with pool.acquire() as conn:
        first = await resolve_oidc_user(conn, _login(), relink_enabled=False)
        again = await resolve_oidc_user(
            conn, _login(email="nouvelle@example.com"), relink_enabled=False
        )
        assert await _user_count(conn) == 1
        email = await conn.fetchval("SELECT email FROM users")
    assert again.user_id == first.user_id
    assert again.owner_id == _owner(EMAIL)  # figé : ne suit pas l'email
    assert email == "nouvelle@example.com"


async def test_new_issuer_with_verified_email_relinks_when_window_open(pool) -> None:
    """Critère 2 : bascule d'émetteur, re-liaison ouverte, historique conservé."""
    async with pool.acquire() as conn:
        first = await resolve_oidc_user(conn, _login(), relink_enabled=False)
        moved = await resolve_oidc_user(
            conn, _login(issuer=ISSUER_B, sub="sub-b-1"), relink_enabled=True
        )
        history = await conn.fetch(
            "SELECT oidc_issuer, replaced_at IS NOT NULL AS replaced "
            "FROM user_oidc_identity_history ORDER BY pinned_at"
        )
    assert moved.user_id == first.user_id and moved.owner_id == first.owner_id
    assert [(h["oidc_issuer"], h["replaced"]) for h in history] == [
        (ISSUER_A, True),
        (ISSUER_B, False),
    ]


async def test_new_issuer_refused_when_relink_window_closed(pool) -> None:
    async with pool.acquire() as conn:
        await resolve_oidc_user(conn, _login(), relink_enabled=False)
        with pytest.raises(OidcIdentityRefusedError) as exc:
            await resolve_oidc_user(
                conn, _login(issuer=ISSUER_B, sub="sub-b-1"), relink_enabled=False
            )
    assert exc.value.reason == "relink_closed"


@pytest.mark.parametrize("relink_enabled", [False, True])
async def test_same_issuer_other_sub_refused_even_with_relink_open(pool, relink_enabled) -> None:
    """Critère 3 : le discriminant est l'émetteur, jamais le mode de re-liaison."""
    async with pool.acquire() as conn:
        await resolve_oidc_user(conn, _login(), relink_enabled=False)
        with pytest.raises(OidcIdentityRefusedError) as exc:
            await resolve_oidc_user(conn, _login(sub="sub-a-2"), relink_enabled=relink_enabled)
        sub = await conn.fetchval("SELECT oidc_sub FROM users")
    assert exc.value.reason == "sub_mismatch"
    assert sub == "sub-a-1"


async def test_unverified_email_cannot_take_over_existing_account(pool) -> None:
    async with pool.acquire() as conn:
        await _local_admin(conn)
        with pytest.raises(OidcIdentityRefusedError) as exc:
            await resolve_oidc_user(conn, _login(email_verified=False), relink_enabled=True)
        anchored = await conn.fetchval("SELECT oidc_sub FROM users")
    assert exc.value.reason == "email_unverified"
    assert anchored is None


async def test_login_without_email_refused(pool) -> None:
    async with pool.acquire() as conn:
        with pytest.raises(OidcIdentityRefusedError) as exc:
            await resolve_oidc_user(conn, _login(email=None), relink_enabled=False)
    assert exc.value.reason == "email_missing"


async def test_role_in_database_never_overwritten_by_token(pool) -> None:
    async with pool.acquire() as conn:
        await resolve_oidc_user(conn, _login(token_roles=("rag-viewer",)), relink_enabled=False)
        user = await resolve_oidc_user(
            conn, _login(token_roles=("rag-admin",)), relink_enabled=False
        )
    assert user.role == "rag-viewer"


async def test_owner_id_frozen_at_insert_and_not_recomputed_on_email_change(pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES ('u', 'A@Example.com', '')"
        )
        await conn.execute("UPDATE users SET email = 'other@example.com'")
        owner = await conn.fetchval("SELECT owner_id FROM users")
    assert owner == _owner("a@example.com")


async def test_migration_099_backfills_existing_users_without_changing_owner(
    session_pool: asyncpg.Pool, tmp_path: Path
) -> None:
    """Base EXISTANTE : les comptes gardent sha256(email) — aucun objet ne change
    de propriétaire ; les comptes locaux deviennent admin, les autres sans rôle."""
    before = tmp_path / "before"
    before.mkdir()
    for sql in MIGRATIONS_DIR.glob("*.sql"):
        if sql.name < "099":
            shutil.copy(sql, before / sql.name)
    await run_migrations(session_pool, before)
    async with session_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO users (username, email, password_hash) VALUES "
            "('local', 'Local@Example.com', 'bcrypt'), ('fed', 'fed@example.com', '')"
        )
    await run_migrations(session_pool, MIGRATIONS_DIR)
    rows = await session_pool.fetch("SELECT username, owner_id, role FROM users ORDER BY username")
    assert [(r["username"], r["owner_id"], r["role"]) for r in rows] == [
        ("fed", _owner("fed@example.com"), None),
        ("local", _owner("local@example.com"), "rag-admin"),
    ]
