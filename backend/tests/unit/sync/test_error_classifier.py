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


# ---------------------------------------------------------------------------
# Backoff strategy
# ---------------------------------------------------------------------------
from rag.sync.executor import _backoff_delay, _should_retry  # noqa: E402


def test_backoff_first_attempt_is_30s() -> None:
    assert _backoff_delay(0) == 30


def test_backoff_doubles_each_time() -> None:
    assert _backoff_delay(1) == 60
    assert _backoff_delay(2) == 120
    assert _backoff_delay(3) == 240


def test_should_retry_true_below_4h() -> None:
    # retry_count=8 -> 30 * 256 = 7680s < 14400s
    assert _should_retry(8) is True


def test_should_retry_false_above_4h() -> None:
    # retry_count=9 -> 30 * 512 = 15360s > 14400s
    assert _should_retry(9) is False
