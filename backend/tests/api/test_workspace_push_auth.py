from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key

# Depuis le passage workspace-en-body : POST /index avec {workspace, path, content}
# (plus de workspace dans l'URL).


def _make_ws(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    scope: str = "read_write",
) -> str:
    """Crée un workspace + clé utilisateur (niveau `scope`) → clé claire."""
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def test_push_returns_404_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Split 401/404 (2026-09-06) : workspace inconnu ≠ problème de sécurité."""
    key = _make_ws(admin_client, admin_headers, "ws_known")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {key}"},
        json={"workspace": "ghost", "path": "doc.md", "content": "x"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_push_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_noauth")
    r = admin_client.post(
        "/api/v1/index",
        json={"workspace": "ws_noauth", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_push_returns_401_wrong_scheme(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_wrongscheme")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": "Basic abc"},
        json={"workspace": "ws_wrongscheme", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_auth_scheme"


def test_push_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_bad_key")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": "Bearer not-the-real-key"},
        json={"workspace": "ws_bad_key", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    # Clé inexistante : rejetée par la dépendance owner.
    assert r.json()["detail"] == "invalid_apikey"


def test_push_returns_202_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_ok")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"workspace": "ws_ok", "path": "docs/foo.md", "content": "hello world"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_push_read_scope_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Une clé de niveau lecture seule ne peut pas pousser d'indexation."""
    read_key = _make_ws(admin_client, admin_headers, "ws_readonly", scope="read")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {read_key}"},
        json={"workspace": "ws_readonly", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    # Problème de sécurité (niveau de clé), distinct du workspace inconnu (404).
    assert r.json()["detail"] == "insufficient_scope"
