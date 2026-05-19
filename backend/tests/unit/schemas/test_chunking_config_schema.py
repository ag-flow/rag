from __future__ import annotations

from uuid import uuid4

import pytest
from pydantic import ValidationError

from rag.schemas.admin import ChunkingConfigResponse, ChunkingConfigSpec


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
    with pytest.raises(ValidationError, match="max_chars"):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=0,
            min_chars=0,
            overlap_chars=0,
            extras={},
        )


def test_min_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError, match="min_chars must be < max_chars"):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=200,
            min_chars=200,
            overlap_chars=50,
            extras={},
        )


def test_overlap_chars_must_be_lt_max_chars() -> None:
    with pytest.raises(ValidationError, match="overlap_chars must be < max_chars"):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=500,
            min_chars=100,
            overlap_chars=500,
            extras={},
        )


def test_strategy_must_be_known_literal() -> None:
    with pytest.raises(ValidationError, match="strategy"):
        ChunkingConfigSpec(
            strategy="unknown",  # type: ignore[arg-type]
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={},
        )


def test_extras_must_be_empty_for_paragraph() -> None:
    with pytest.raises(ValidationError, match="extras must be empty for strategy 'paragraph'"):
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


def test_extras_defaults_to_empty_dict() -> None:
    """Omitting `extras=` produces {} via default_factory=dict."""
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
    )
    assert spec.extras == {}


def test_unknown_field_rejected() -> None:
    """`extra='forbid'` on ChunkingConfigSpec rejects unknown fields."""
    with pytest.raises(ValidationError, match=r"extra_forbidden|Extra inputs"):
        ChunkingConfigSpec(
            strategy="paragraph",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={},
            unknown_field="x",  # type: ignore[call-arg]
        )


def test_chunking_config_response_instantiates_from_db_row_shape() -> None:
    """ChunkingConfigResponse instancie depuis une row DB typique."""
    response = ChunkingConfigResponse(
        workspace_id=uuid4(),
        strategy="paragraph",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={},
        created_at="2026-05-18T10:00:00Z",
        updated_at="2026-05-18T10:00:00Z",
    )
    assert response.strategy == "paragraph"
    assert response.extras == {}


def test_markdown_happy_path_default_extras() -> None:
    """extras={} accepté, normalisé en {heading_levels:[1,2]}."""
    spec = ChunkingConfigSpec(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={},
    )
    assert spec.strategy == "markdown"
    assert spec.extras == {"heading_levels": [1, 2]}


def test_markdown_custom_heading_levels() -> None:
    spec = ChunkingConfigSpec(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={"heading_levels": [1, 2, 3]},
    )
    assert spec.extras == {"heading_levels": [1, 2, 3]}


def test_markdown_rejects_unknown_extras_key() -> None:
    with pytest.raises(ValidationError, match="unknown keys"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"foo": "bar"},
        )


def test_markdown_rejects_empty_heading_levels() -> None:
    with pytest.raises(ValidationError, match="non-empty list"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"heading_levels": []},
        )


def test_markdown_rejects_out_of_range_levels() -> None:
    with pytest.raises(ValidationError, match=r"in \[1, 6\]"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"heading_levels": [0]},
        )
    with pytest.raises(ValidationError, match=r"in \[1, 6\]"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"heading_levels": [7]},
        )


def test_markdown_rejects_unsorted_levels() -> None:
    with pytest.raises(ValidationError, match="sorted ascending"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"heading_levels": [2, 1]},
        )


def test_markdown_rejects_duplicate_levels() -> None:
    with pytest.raises(ValidationError, match="duplicates"):
        ChunkingConfigSpec(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"heading_levels": [1, 1]},
        )
