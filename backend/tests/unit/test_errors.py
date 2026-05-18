from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.errors import (
    ChunkingChangeRequiresReindex,
    IndexerChangeRequiresReindex,
    ModelInUse,
    ModelNotSupported,
    PatchFieldNotAllowed,
    RefNotFoundInVault,
    SourceNotFound,
    SourceTypeNotSupported,
    VaultUnreachable,
    WorkspaceAlreadyExists,
    WorkspaceNotFound,
    register_error_handlers,
)


def _make_app_raising(exc: Exception) -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/boom")
    def boom() -> None:
        raise exc

    return app


def test_workspace_not_found_maps_404() -> None:
    client = TestClient(_make_app_raising(WorkspaceNotFound("ws-x")))
    r = client.get("/boom")
    assert r.status_code == 404
    assert r.json() == {"error": "workspace_not_found", "name": "ws-x"}


def test_workspace_already_exists_maps_409() -> None:
    client = TestClient(_make_app_raising(WorkspaceAlreadyExists("ws-x")))
    r = client.get("/boom")
    assert r.status_code == 409
    assert r.json() == {"error": "workspace_already_exists", "name": "ws-x"}


def test_model_not_supported_maps_422() -> None:
    client = TestClient(
        _make_app_raising(
            ModelNotSupported(
                provider="p", model="m", supported=[("openai", "text-embedding-3-small")]
            )
        )
    )
    r = client.get("/boom")
    assert r.status_code == 422
    body = r.json()
    assert body["error"] == "model_not_supported"
    assert body["provider"] == "p"
    assert body["model"] == "m"
    assert body["supported"] == [["openai", "text-embedding-3-small"]]


def test_ref_not_found_in_vault_maps_422() -> None:
    client = TestClient(_make_app_raising(RefNotFoundInVault("openai_embedding_key")))
    r = client.get("/boom")
    assert r.status_code == 422
    assert r.json() == {"error": "ref_not_found_in_vault", "ref": "openai_embedding_key"}


def test_vault_unreachable_maps_503() -> None:
    client = TestClient(_make_app_raising(VaultUnreachable()))
    r = client.get("/boom")
    assert r.status_code == 503
    assert r.json() == {"error": "vault_unreachable"}


def test_indexer_change_requires_reindex_maps_409() -> None:
    client = TestClient(
        _make_app_raising(
            IndexerChangeRequiresReindex(
                workspace="ws",
                current="openai/text-embedding-3-small (dim=1536)",
                requested="voyage/voyage-3 (dim=1024)",
                documents_count=61,
            )
        )
    )
    r = client.get("/boom")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "indexer_change_requires_reindex"
    assert body["documents_count"] == 61
    assert body["action"] == "POST /workspaces/ws/reindex?confirm=true"


def test_chunking_change_requires_reindex_maps_409() -> None:
    client = TestClient(
        _make_app_raising(
            ChunkingChangeRequiresReindex(
                workspace="ws",
                current="paragraph (max=2000, min=200, overlap=200)",
                new="paragraph (max=1500, min=100, overlap=150)",
            )
        )
    )
    r = client.get("/boom")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "chunking_change_requires_reindex"
    assert body["workspace"] == "ws"
    assert body["current"] == "paragraph (max=2000, min=200, overlap=200)"
    assert body["new"] == "paragraph (max=1500, min=100, overlap=150)"
    assert body["action"] == "PUT /workspaces/ws/chunking-config?confirm=true"


def test_source_not_found_maps_404() -> None:
    client = TestClient(_make_app_raising(SourceNotFound("src-id-1")))
    r = client.get("/boom")
    assert r.status_code == 404
    assert r.json() == {"error": "source_not_found", "id": "src-id-1"}


def test_source_type_not_supported_maps_422() -> None:
    client = TestClient(_make_app_raising(SourceTypeNotSupported("confluence")))
    r = client.get("/boom")
    assert r.status_code == 422
    assert r.json() == {
        "error": "source_type_not_supported",
        "type": "confluence",
        "supported": ["git"],
    }


def test_model_in_use_maps_409() -> None:
    client = TestClient(_make_app_raising(ModelInUse("openai", "m", ["ws1", "ws2"])))
    r = client.get("/boom")
    assert r.status_code == 409
    body = r.json()
    assert body["error"] == "model_in_use"
    assert sorted(body["workspaces"]) == ["ws1", "ws2"]


def test_patch_field_not_allowed_maps_422() -> None:
    client = TestClient(_make_app_raising(PatchFieldNotAllowed("name")))
    r = client.get("/boom")
    assert r.status_code == 422
    assert r.json() == {"error": "patch_field_not_allowed", "field": "name"}
