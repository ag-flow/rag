from __future__ import annotations

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace et retourne l'api_key clair."""
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


def _stub_indexer(client: TestClient) -> object:
    """Remplace `app.state.indexer` par un fake qui retourne chunks=2."""

    class _Fake:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        async def index_file(self, **kw):  # type: ignore[no-untyped-def]
            self.calls.append(kw)
            return 2

        async def delete_file(self, **kw):  # type: ignore[no-untyped-def]
            raise AssertionError("delete_file not expected here")

    fake = _Fake()
    client.app.state.indexer = fake  # type: ignore[attr-defined]
    return fake


def test_push_returns_404_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ghost/index",
        headers={"Authorization": "Bearer some-key"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "workspace_not_found"


def test_push_returns_401_without_authorization(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_noauth")
    _stub_indexer(admin_client)
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
    _stub_indexer(admin_client)
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
    _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_bad_key/index",
        headers={"Authorization": "Bearer not-the-real-key"},
        json={"path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_push_returns_200_with_valid_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_ok")
    fake = _stub_indexer(admin_client)
    r = admin_client.post(
        "/workspaces/ws_ok/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "docs/foo.md", "content": "hello world"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "indexed"
    assert body["path"] == "docs/foo.md"
    assert body["chunks"] == 2
    assert body["hash"].startswith("sha256:")
    assert len(fake.calls) == 1
    assert fake.calls[0]["indexer_used"] == "openai/text-embedding-3-small"


def test_push_cross_workspace_key_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_a")
    _make_ws(admin_client, admin_headers, "ws_b")
    _stub_indexer(admin_client)
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
    _stub_indexer(admin_client)

    # 1er push : succès avec v1 → met en cache
    r = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "x"},
    )
    assert r.status_code == 200

    # rotate la clé
    r2 = admin_client.post("/api/admin/workspaces/ws_rot/rotate-apikey", headers=admin_headers)
    assert r2.status_code == 200

    # push avec l'ancienne clé : doit échouer 401 (cache invalidé + nouveau hash en DB)
    r3 = admin_client.post(
        "/workspaces/ws_rot/index",
        headers={"Authorization": f"Bearer {api_key_v1}"},
        json={"path": "a.md", "content": "y"},
    )
    assert r3.status_code == 401
