from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.errors import (
    AdminError,
    ContentTooLarge,
    EmbeddingProviderUnavailable,
    InvalidPath,
    register_error_handlers,
)
from rag.schemas.workspace import PushRequest


def test_invalid_path_payload_includes_reason() -> None:
    e = InvalidPath("path_traversal_forbidden")
    assert isinstance(e, AdminError)
    assert e.http_status == 422
    assert e.to_payload() == {
        "error": "invalid_path",
        "reason": "path_traversal_forbidden",
    }


def test_content_too_large_payload_includes_limit() -> None:
    e = ContentTooLarge()
    assert isinstance(e, AdminError)
    assert e.http_status == 413
    assert e.to_payload() == {
        "error": "content_too_large",
        "limit_bytes": 5 * 1024 * 1024,
    }


def test_embedding_provider_unavailable_payload() -> None:
    e = EmbeddingProviderUnavailable("openai", "rate_limited")
    assert isinstance(e, AdminError)
    assert e.http_status == 502
    assert e.to_payload() == {
        "error": "embedding_provider_error",
        "provider": "openai",
        "reason": "rate_limited",
    }


# ---------------------------------------------------------------------------
# Tests d'intégration : _validation_handler (branching 413 vs 422)
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.post("/echo")
    def echo(_body: PushRequest) -> dict[str, str]:
        return {"ok": "true"}

    return app


def test_validation_handler_remaps_content_too_large_to_413() -> None:
    client = TestClient(_make_app())
    big = "a" * (5 * 1024 * 1024 + 1)
    r = client.post("/echo", json={"path": "x.md", "content": big})
    assert r.status_code == 413
    assert r.json() == {"error": "content_too_large", "limit_bytes": 5 * 1024 * 1024}


def test_validation_handler_keeps_other_errors_as_422() -> None:
    client = TestClient(_make_app())
    # path: "" → min_length=1 violated, content manquant → both fail
    r = client.post("/echo", json={"path": "", "content": ""})
    assert r.status_code == 422
    body = r.json()
    assert "detail" in body
    # Ne pas vérifier le contenu exact de "detail" pour être robuste aux
    # changements mineurs de format Pydantic v2.
