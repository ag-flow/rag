"""Écran Utilisateurs : liste et rôles des comptes (ticket a138f63b).

Deux navigateurs (deux TestClient sur la même app) : l'admin de bootstrap et
un second compte local, pour éprouver qu'une rétrogradation s'applique à la
requête suivante de l'autre session, sans reconnexion.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import asyncpg
import bcrypt
import pytest
from fastapi.testclient import TestClient

from tests.api._helpers import make_app_client

_PASSWORD = "pw-for-tests-123"
_USERS = "/api/admin/users"


def _insert_local_user(dsn: str, username: str, role: str | None) -> None:
    async def _run() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute(
                "INSERT INTO users (username, email, password_hash, role) VALUES ($1, $2, $3, $4)",
                username,
                f"{username}@example.com",
                bcrypt.hashpw(_PASSWORD.encode(), bcrypt.gensalt(4)).decode(),
                role,
            )
        finally:
            await conn.close()

    asyncio.run(_run())


def _login(client: TestClient, username: str) -> None:
    resp = client.post("/auth/local/login", json={"username": username, "password": _PASSWORD})
    assert resp.status_code == 200, resp.text


class _Browser:
    """Un navigateur = un jeu de cookies de session, sur le client partagé.

    Un seul TestClient (et donc une seule boucle d'événements, celle des pools
    asyncpg) ; changer de navigateur = changer de cookies.
    """

    def __init__(self, client: TestClient, cookies: dict[str, str]) -> None:
        self._client = client
        self._cookies = cookies

    def _use(self) -> TestClient:
        self._client.cookies.clear()
        self._client.cookies.update(self._cookies)
        return self._client

    def get(self, url: str):  # type: ignore[no-untyped-def]
        return self._use().get(url)

    def patch(self, url: str, json: object):  # type: ignore[no-untyped-def]
        return self._use().patch(url, json=json)


def _session_cookies(client: TestClient, username: str) -> dict[str, str]:
    client.cookies.clear()
    _login(client, username)
    return dict(client.cookies)


@pytest.fixture
def two_sessions(pg_container: str) -> Iterator[tuple[_Browser, _Browser, str]]:
    """(admin de bootstrap, second compte local admin, id du second)."""
    with make_app_client(pg_container) as client:
        client.post(
            "/api/setup/init-admin",
            json={"username": "boot", "email": "boot@example.com", "password": _PASSWORD},
        )
        _insert_local_user(pg_container, "bob", "rag-admin")
        admin = _Browser(client, _session_cookies(client, "boot"))
        bob = _Browser(client, _session_cookies(client, "bob"))
        bob_id = next(u["id"] for u in admin.get(_USERS).json() if u["username"] == "bob")
        yield admin, bob, bob_id


def _role(browser: _Browser, user_id: str, role: str | None):  # type: ignore[no-untyped-def]
    return browser.patch(f"{_USERS}/{user_id}/role", json={"role": role})


def test_admin_lists_accounts_with_type_and_role(two_sessions) -> None:
    admin, _bob, _ = two_sessions
    users = {u["username"]: u for u in admin.get(_USERS).json()}
    assert users["boot"]["role"] == "rag-admin"
    assert users["boot"]["has_local_password"] is True
    assert users["boot"]["oidc_issuer"] is None


def test_demoted_local_session_loses_admin_on_next_request(two_sessions) -> None:
    admin, bob, bob_id = two_sessions
    assert bob.get(_USERS).status_code == 200

    resp = _role(admin, bob_id, "rag-viewer")
    assert resp.status_code == 200 and resp.json()["role"] == "rag-viewer"
    # Même session, aucune reconnexion : les droits ont déjà changé.
    assert bob.get(_USERS).status_code == 403
    assert bob.get("/me").json()["roles"] == ["rag-viewer"]


def test_access_removed_leaves_no_role(two_sessions) -> None:
    admin, bob, bob_id = two_sessions
    assert _role(admin, bob_id, None).json()["role"] is None
    assert bob.get(_USERS).status_code == 403
    assert bob.get("/me").json()["roles"] == []


def test_last_admin_cannot_be_demoted(two_sessions) -> None:
    admin, _bob, bob_id = two_sessions
    boot_id = next(u["id"] for u in admin.get(_USERS).json() if u["username"] == "boot")
    assert _role(admin, bob_id, "rag-viewer").status_code == 200
    resp = _role(admin, boot_id, "rag-viewer")
    assert resp.status_code == 409
    assert resp.json()["detail"] == "last_admin"
    roles = {u["username"]: u["role"] for u in admin.get(_USERS).json()}
    assert roles["boot"] == "rag-admin"


def test_unknown_user_and_invalid_role_rejected(two_sessions) -> None:
    admin, _bob, bob_id = two_sessions
    missing = "00000000-0000-0000-0000-000000000000"
    assert _role(admin, missing, "rag-viewer").status_code == 404
    assert _role(admin, bob_id, "superuser").status_code == 422


def test_anonymous_refused(pg_container: str) -> None:
    with make_app_client(pg_container) as client:
        assert client.get(_USERS).status_code == 401
