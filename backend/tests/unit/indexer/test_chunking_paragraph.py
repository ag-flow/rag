from __future__ import annotations

import pytest

from rag.indexer.chunking import Chunk, ParagraphChunker


def _default() -> ParagraphChunker:
    return ParagraphChunker(max_chars=2000, min_chars=200, overlap_chars=200)


def test_empty_returns_empty() -> None:
    assert _default().chunk("") == []


def test_whitespace_only_returns_empty() -> None:
    assert _default().chunk("   \n\n   \n\n   ") == []


def test_short_content_returns_single_chunk() -> None:
    result = _default().chunk("hello world")
    assert len(result) == 1
    assert result[0].content == "hello world"
    assert result[0].metadata == {}


def test_two_short_paragraphs_are_coalesced() -> None:
    content = "Paragraphe un.\n\nParagraphe deux."
    result = _default().chunk(content)
    assert len(result) == 1
    assert "Paragraphe un." in result[0].content
    assert "Paragraphe deux." in result[0].content
    assert result[0].metadata == {}


def test_two_long_paragraphs_split_with_overlap() -> None:
    para_a = "A" * 1500
    para_b = "B" * 1500
    content = f"{para_a}\n\n{para_b}"
    result = ParagraphChunker(
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2
    contents = [c.content for c in result]
    for i in range(1, len(contents)):
        assert any(contents[i].startswith(contents[i - 1][-k:]) for k in range(50, 201))
    for c in result:
        assert c.metadata == {}


def test_giant_paragraph_split_on_separator() -> None:
    content = "Phrase courte. " * 200
    result = ParagraphChunker(
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2
    for c in result:
        assert len(c.content) <= 2200
        assert c.metadata == {}


def test_code_no_paragraph_splits_on_newline() -> None:
    content = "\n".join([f"line {i}" for i in range(500)])
    result = ParagraphChunker(
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
    ).chunk(content)
    assert len(result) >= 2


def test_overlap_ge_max_raises() -> None:
    with pytest.raises(ValueError, match="overlap_chars"):
        ParagraphChunker(max_chars=200, min_chars=50, overlap_chars=200).chunk("x")


def test_chunk_metadata_is_always_empty_dict() -> None:
    chunks = _default().chunk("alpha\n\nbeta gamma\n\ndelta")
    for c in chunks:
        assert isinstance(c, Chunk)
        assert c.metadata == {}
