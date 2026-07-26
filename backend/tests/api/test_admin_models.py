from __future__ import annotations

from fastapi.testclient import TestClient


def test_get_models_returns_seed(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.get("/api/admin/models", headers=admin_headers)
    assert r.status_code == 200
    couples = {(e["provider"], e["model"]) for e in r.json()}
    assert ("openai", "text-embedding-3-small") in couples


def test_post_model_201(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"provider": "custom", "model": "m-e2e-1", "dimension": 256},
    )
    assert r.status_code == 201


def test_post_model_rerank_201_and_listed(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"provider": "custom", "model": "m-rerank-1", "kind": "rerank"},
    )
    assert r.status_code == 201
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    entry = next(e for e in entries if e["model"] == "m-rerank-1")
    assert entry["kind"] == "rerank"
    assert entry["dimension"] is None


def test_get_models_includes_rerank_seed(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """La migration 080 seed les modèles de rerank connus (référentiel unique)."""
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    rerank = {(e["provider"], e["model"]) for e in entries if e["kind"] == "rerank"}
    assert ("cohere", "rerank-v3.5") in rerank
    assert ("ollama", "bge-reranker-v2-m3") in rerank


def test_post_model_409_duplicate(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    r = admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"provider": "openai", "model": "text-embedding-3-small", "dimension": 1536},
    )
    assert r.status_code == 409


def test_delete_model_204(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"provider": "custom", "model": "m-e2e-del", "dimension": 64},
    )
    r = admin_client.delete("/api/admin/models/custom/m-e2e-del", headers=admin_headers)
    assert r.status_code == 204


def test_delete_model_409_in_use(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_uses_model",
            "label": "ws_uses_model",
            "endpoint_id": admin_client.default_endpoint_id,
        },
    )
    # Depuis la migration 064 les seeds sont du catalogue système (owner NULL) :
    # la garde d'immutabilité passe AVANT le contrôle « in use ».
    r = admin_client.delete(
        "/api/admin/models/openai/text-embedding-3-small", headers=admin_headers
    )
    assert r.status_code == 403
    assert r.json()["error"] == "model_system_immutable"
