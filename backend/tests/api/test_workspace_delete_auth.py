from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key

# Suppression : DELETE /index avec {workspace, path} dans le corps (httpx n'expose
# pas json= sur .delete() → on passe par .request("DELETE", ...)).


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


def _delete(client: TestClient, *, key: str | None, workspace: str, path: str):
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return client.request(
        "DELETE", "/index", headers=headers, json={"workspace": workspace, "path": path}
    )


def test_delete_returns_401_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = _delete(admin_client, key="nonexistent_key_xyz", workspace="ghost", path="doc.md")
    assert r.status_code == 401
    # Clé inexistante : rejetée par la dépendance owner.
    assert r.json()["detail"] == "invalid_apikey"


def test_delete_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_noauth")
    r = _delete(admin_client, key=None, workspace="ws_del_noauth", path="doc.md")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_delete_returns_401_for_invalid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_del_bad_key")
    r = _delete(admin_client, key="not-the-real-key", workspace="ws_del_bad_key", path="doc.md")
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_apikey"


def test_delete_returns_202_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_ok")
    r = _delete(admin_client, key=api_key, workspace="ws_del_ok", path="docs/foo.md")
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "pending"
    assert "job_id" in body
    assert "X-Correlation-ID" in r.headers


def test_delete_read_scope_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Une clé de niveau lecture seule ne peut pas supprimer (écriture)."""
    read_key = _make_ws(admin_client, admin_headers, "ws_del_readonly", scope="read")
    r = _delete(admin_client, key=read_key, workspace="ws_del_readonly", path="doc.md")
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_delete_nested_path(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_del_nested")
    r = _delete(admin_client, key=api_key, workspace="ws_del_nested", path="a/b/c/deep.md")
    assert r.status_code == 202, r.text
