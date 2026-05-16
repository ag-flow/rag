from __future__ import annotations

from fastapi.testclient import TestClient


def test_post_oidc_creates_config(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client_id"] == "rag-service"


def test_get_oidc_returns_503_when_not_configured(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_post_then_get_returns_same_config(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "ref1",
        },
    )
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["client_secret_ref"] == "ref1"


def test_post_replaces_existing_config(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc-old/realms/r",
            "client_id": "old",
            "client_secret_ref": "old_ref",
        },
    )
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc-new/realms/r",
            "client_id": "new",
            "client_secret_ref": "new_ref",
        },
    )
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    body = r.json()
    assert body["client_id"] == "new"
    assert body["client_secret_ref"] == "new_ref"


def test_post_without_master_key_returns_401(
    admin_client: TestClient,
) -> None:
    r = admin_client.post(
        "/admin/oidc",
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 401


def test_post_422_for_invalid_issuer(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "not-a-url",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 422
