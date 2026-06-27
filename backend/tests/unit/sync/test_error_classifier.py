from __future__ import annotations

from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProviderError,
    EmbeddingProviderUnreachable,
    EmbeddingQuotaExhausted,
    EmbeddingRateLimited,
)
from rag.sync.error_classifier import classify_indexer_error


def test_rate_limited_is_transient() -> None:
    assert classify_indexer_error(EmbeddingRateLimited("429")) == "transient"


def test_unreachable_is_transient() -> None:
    assert classify_indexer_error(EmbeddingProviderUnreachable("503")) == "transient"


def test_auth_error_is_blocking() -> None:
    assert classify_indexer_error(EmbeddingAuthError("401")) == "blocking"


def test_quota_exhausted_is_blocking() -> None:
    assert classify_indexer_error(EmbeddingQuotaExhausted("402")) == "blocking"


def test_generic_provider_error_is_permanent() -> None:
    assert classify_indexer_error(EmbeddingProviderError("unknown")) == "permanent"


def test_runtime_error_is_permanent() -> None:
    assert classify_indexer_error(RuntimeError("db exploded")) == "permanent"


def test_value_error_is_permanent() -> None:
    assert classify_indexer_error(ValueError("bad content")) == "permanent"
