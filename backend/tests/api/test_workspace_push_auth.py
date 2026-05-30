from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace et retourne l'api_key clair."""
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


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


def test_rotate_apikey_invalidates_cache(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key_v1 = _make_ws(admin_client, admin_headers, "ws_rot")

    # 1er push : succes avec v1 → met en cache
    r = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "x"},
    )
    assert r.status_code == 202

    # rotate la cle
    r2 = admin_client.post("/api/admin/workspaces/ws_rot/rotate-apikey", headers=admin_headers)
    assert r2.status_code == 200

    # push avec l'ancienne cle : doit echouer 401 (cache invalide + nouveau hash en DB)
    r3 = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "y"},
    )
    assert r3.status_code == 401
