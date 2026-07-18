from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace + clé utilisateur avec grant d'écriture → clé claire."""
    _, api_key = make_ws_with_user_key(client, admin_headers, name)
    return api_key


def test_push_returns_401_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.post(
        "/workspaces/ghost/index",
        headers={"Authorization": "Bearer nonexistent_key_xyz"},
        json={"path": "doc.md", "content": "x"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_push_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_noauth")
    r = admin_client.post(
        "/workspaces/ws_noauth/index",
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_push_returns_401_wrong_scheme(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_wrongscheme")
    r = admin_client.post(
        "/workspaces/ws_wrongscheme/index",
        headers={"Authorization": "Basic abc"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_auth_scheme"


def test_push_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_bad_key")
    r = admin_client.post(
        "/workspaces/ws_bad_key/index",
        headers={"Authorization": "Bearer not-the-real-key"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_push_returns_202_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_ok")
    r = admin_client.post(
        "/workspaces/ws_ok/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "docs/foo.md", "content": "hello world"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_push_cross_workspace_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_a")
    _make_ws(admin_client, admin_headers, "ws_b")
    r = admin_client.post(
        "/workspaces/ws_b/index",
        headers={"Authorization": f"Bearer {key_a}"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


# test_rotate_apikey_invalidates_cache supprimé : la rotation d'api_key PAR
# WORKSPACE (POST /api/admin/workspaces/{name}/rotate-apikey) n'existe plus
# depuis le chantier clés utilisateur (444308a) — la rotation est couverte
# côté clés user dans test_me_api_keys.py.
