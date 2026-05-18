from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.admin import ChunkingConfigSpec


def test_paragraph_happy_path() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={},
    )
    assert spec.strategy == "paragraph"
    assert spec.max_chars == 2000


def test_max_chars_must_be_positive() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=0,
            min_chars=0,
            overlap_chars=0,
            extras={},
        )


def test_min_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=200,
            min_chars=200,
            overlap_chars=50,
            extras={},
        )


def test_overlap_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=500,
            min_chars=100,
            overlap_chars=500,
            extras={},
        )


def test_strategy_must_be_paragraph() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={},
        )


def test_extras_must_be_empty_for_paragraph() -> None:
    with pytest.raises(ValidationError):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"foo": "bar"},
        )


def test_min_chars_can_be_zero() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1000,
        min_chars=0,
        overlap_chars=100,
        extras={},
    )
    assert spec.min_chars == 0


def test_overlap_chars_can_be_zero() -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1000,
        min_chars=100,
        overlap_chars=0,
        extras={},
    )
    assert spec.overlap_chars == 0
