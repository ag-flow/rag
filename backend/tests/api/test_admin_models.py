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
    # Migration 083 : rerankers cloud.
    assert ("fireworks", "accounts/fireworks/models/qwen3-reranker-8b") in rerank
    assert ("deepinfra", "Qwen/Qwen3-Reranker-8B") in rerank
    assert ("mixedbread", "mxbai-rerank-large-v2") in rerank
    # Migration 088 : Cohere Rerank v4.0 via Azure Foundry.
    assert ("azure-foundry", "Cohere-rerank-v4.0-fast") in rerank


def test_get_models_includes_llm_enrichment_seed(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """La migration 084 seed les LLM d'enrichissement (batch coût/qualité)."""
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    llm = {(e["provider"], e["model"]) for e in entries if e["kind"] == "llm"}
    assert ("openai", "gpt-4.1-nano") in llm
    assert ("claude", "claude-haiku-4-5") in llm
    assert ("gemini", "gemini-2.5-flash") in llm
    assert ("deepseek", "deepseek-v4-flash") in llm
    assert ("dashscope", "qwen3.7-max") in llm


def test_get_models_includes_cloud_embedding_seed(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """La migration 082 seed les embeddings cloud (cohere, fireworks,
    deepinfra, together, bedrock)."""
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    embed = {
        (e["provider"], e["model"]): e["dimension"]
        for e in entries
        if e["kind"] == "embedding"
    }
    assert embed[("cohere", "embed-v4")] == 1536
    assert embed[("deepinfra", "BAAI/bge-m3")] == 1024
    assert embed[("together", "intfloat/multilingual-e5-large-instruct")] == 1024
    assert embed[("bedrock", "amazon.titan-embed-text-v2:0")] == 1024
    assert embed[("fireworks", "nomic-ai/nomic-embed-text-v1.5")] == 768


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


def test_get_rerank_pairings_returns_seed(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    """La migration 085 seed les préconisations embedder → reranker."""
    r = admin_client.get("/api/admin/models/rerank-pairings", headers=admin_headers)
    assert r.status_code == 200
    pairings = r.json()
    assert len(pairings) >= 7
    cohere = next(p for p in pairings if p["embed_provider_like"] == "cohere")
    assert cohere["rerank_model_like"] == "rerank-%"
    assert cohere["note"]
    qwen = next(p for p in pairings if "qwen3-embedding" in p["embed_model_like"])
    assert qwen["rerank_model_like"] == "%qwen3-reranker%"


def test_get_provider_url_templates(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/api/admin/providers/url-templates", headers=admin_headers)
    assert r.status_code == 200
    templates = r.json()
    azure = templates["azure-openai"]["embeddings"]
    assert azure["template"] == (
        "{base_url}/openai/deployments/{model}/embeddings?api-version=2024-02-01"
    )
    assert templates["openai"]["embeddings"]["default_base_url"] == "https://api.openai.com/v1"


def test_post_model_with_url_template_roundtrip(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={
            "provider": "azure-openai",
            "model": "m-azure-deploy",
            "dimension": 3072,
            "url_template": "{url}/openai/deployments/mon-deploiement/embeddings"
            "?api-version=2024-02-01",
        },
    )
    assert r.status_code == 201
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    entry = next(e for e in entries if e["model"] == "m-azure-deploy")
    assert "mon-deploiement" in entry["url_template"]


def test_patch_model_updates_owned_entry(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/api/admin/models",
        headers=admin_headers,
        json={"provider": "custom", "model": "m-patch-1", "dimension": 256},
    )
    r = admin_client.patch(
        "/api/admin/models/custom/m-patch-1",
        headers=admin_headers,
        json={"kind": "embedding", "dimension": 512, "url_template": "{url}/embed"},
    )
    assert r.status_code == 200
    entries = admin_client.get("/api/admin/models", headers=admin_headers).json()
    entry = next(e for e in entries if e["model"] == "m-patch-1")
    assert entry["dimension"] == 512
    assert entry["url_template"] == "{url}/embed"


def test_patch_model_system_entry_forbidden(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.patch(
        "/api/admin/models/openai/text-embedding-3-small",
        headers=admin_headers,
        json={"kind": "embedding", "dimension": 1536},
    )
    assert r.status_code == 403


def test_patch_model_unknown_404(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.patch(
        "/api/admin/models/nope/nope-model",
        headers=admin_headers,
        json={"kind": "llm"},
    )
    assert r.status_code == 404
