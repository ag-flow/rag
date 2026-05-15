from __future__ import annotations

from rag.api.errors import (
    AdminError,
    ContentTooLarge,
    EmbeddingProviderUnavailable,
    InvalidPath,
)


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
