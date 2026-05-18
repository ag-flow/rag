from __future__ import annotations

import pytest

from rag.indexer.chunking import ParagraphChunker, make_chunker


def test_make_chunker_paragraph_returns_paragraph_chunker() -> None:
    chunker = make_chunker(
        strategy="paragraph",
        max_chars=1500,
        min_chars=150,
        overlap_chars=150,
        extras={},
    )
    assert isinstance(chunker, ParagraphChunker)


def test_make_chunker_paragraph_uses_params() -> None:
    chunker = make_chunker(
        strategy="paragraph",
        max_chars=500,
        min_chars=50,
        overlap_chars=50,
        extras={},
    )
    chunks = chunker.chunk("Phrase. " * 200)
    assert len(chunks) >= 2


def test_make_chunker_unknown_strategy_raises() -> None:
    with pytest.raises(ValueError, match="unknown chunking strategy: foo"):
        make_chunker(
            strategy="foo",
            max_chars=1000,
            min_chars=100,
            overlap_chars=100,
            extras={},
        )


def test_make_chunker_paragraph_rejects_non_empty_extras() -> None:
    with pytest.raises(ValueError, match="paragraph strategy does not accept extras"):
        make_chunker(
            strategy="paragraph",
            max_chars=1000,
            min_chars=100,
            overlap_chars=100,
            extras={"foo": "bar"},
        )
