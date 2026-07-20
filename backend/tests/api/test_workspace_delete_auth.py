from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


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


def test_delete_returns_401_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.delete(
        "/workspaces/ghost/index/doc.md",
        headers={"Authorization": "Bearer nonexistent_key_xyz"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_noauth")
    r = admin_client.delete("/workspaces/ws_del_noauth/index/doc.md")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_delete_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_bad_key")
    r = admin_client.delete(
        "/workspaces/ws_del_bad_key/index/doc.md",
        headers={"Authorization": "Bearer not-the-real-key"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_returns_202_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_ok")
    r = admin_client.delete(
        "/workspaces/ws_del_ok/index/docs/foo.md",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_delete_read_scope_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Une clé de niveau lecture seule ne peut pas supprimer (écriture).

    Le modèle par workspace ayant disparu (migration 067 : accès global), le
    refus d'écriture s'exprime désormais par le niveau `scope='read'`.
    """
    read_key = _make_ws(admin_client, admin_headers, "ws_del_readonly", scope="read")
    r = admin_client.delete(
        "/workspaces/ws_del_readonly/index/doc.md",
        headers={"Authorization": f"Bearer {read_key}"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_nested_path(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_nested")
    r = admin_client.delete(
        "/workspaces/ws_del_nested/index/a/b/c/deep.md",
        headers={"Authorization": f"Bearer {api_key}"},
    )
    assert r.status_code == 202, r.text
