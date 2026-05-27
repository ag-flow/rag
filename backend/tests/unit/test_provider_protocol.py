from __future__ import annotations

import inspect

import pytest

from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)


def test_embedding_provider_protocol_has_embed_texts() -> None:
    """Le Protocol définit bien `embed_texts(texts) -> list[list[float]]` async."""
    method = inspect.getattr_static(EmbeddingProvider, "embed_texts")
    assert inspect.iscoroutinefunction(method)


def test_exception_hierarchy() -> None:
    """Toutes les exceptions provider héritent de EmbeddingProviderError."""
    assert issubclass(EmbeddingAuthError, EmbeddingProviderError)
    assert issubclass(EmbeddingRateLimited, EmbeddingProviderError)
    assert issubclass(EmbeddingProviderUnreachable, EmbeddingProviderError)
    assert issubclass(EmbeddingProviderError, RuntimeError)


def test_embedding_auth_error_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingAuthError("401 unauthorized")


def test_embedding_rate_limited_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingRateLimited("429 too many")


def test_embedding_provider_unreachable_can_be_raised_and_caught() -> None:
    with pytest.raises(EmbeddingProviderError):
        raise EmbeddingProviderUnreachable("timeout")
