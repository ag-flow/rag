from __future__ import annotations

from fastapi.testclient import TestClient


def _make_user_key(
    client, admin_headers: dict[str, str], ws_id: str, name: str
) -> str:
    """Crée une clé utilisateur de niveau écriture (accès global)."""
    kr = client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": f"key-{name}", "scope": "read_write"},
    )
    assert kr.status_code == 201, kr.text
    return kr.json()["api_key"]


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": name, "label": name, "endpoint_id": client.default_endpoint_id},
    )
    assert r.status_code == 201
    return _make_user_key(client, admin_headers, r.json()["id"], name)


def test_push_returns_422_for_path_traversal(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_a")
    r = admin_client.post(
        "/workspaces/ws_e_a/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "foo/../bar", "content": "y"},
    )
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "invalid_path"
    assert body["reason"] == "path_traversal_forbidden"


def test_push_returns_422_for_absolute_path(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_b")
    r = admin_client.post(
        "/workspaces/ws_e_b/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "/etc/passwd", "content": "y"},
    )
    assert r.status_code == 422
    assert r.json()["error"] == "invalid_path"


def test_push_returns_422_for_missing_body_field(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_c")
    r = admin_client.post(
        "/workspaces/ws_e_c/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "x.md"},  # content manquant
    )
    assert r.status_code == 422


def test_push_returns_413_for_content_above_5mb(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_e_d")
    # Pydantic validator lève ValueError("content_too_large") → handler
    # custom remap en 413 avec payload ContentTooLarge.
    big = "a" * (5 * 1024 * 1024 + 1)
    r = admin_client.post(
        "/workspaces/ws_e_d/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": "big.md", "content": big},
    )
    assert r.status_code == 413
    body = r.json()
    assert body["error"] == "content_too_large"
    assert body["limit_bytes"] == 5 * 1024 * 1024


def test_push_returns_422_for_other_validation_errors_unchanged(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Regression : le handler RequestValidationError ne doit pas hijacker
    les autres erreurs de validation (champ manquant, mauvais type, etc.)."""
    api_key = _make_ws(admin_client, admin_headers, "ws_e_e")
    r = admin_client.post(
        "/workspaces/ws_e_e/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"path": 123, "content": "x"},  # path: int au lieu de str
    )
    assert r.status_code == 422
    body = r.json()
    # Format Pydantic standard : {"detail": [...]}
    assert "detail" in body
