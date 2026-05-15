from __future__ import annotations

import pytest

from rag.indexer.chunking import chunk_text


def test_chunk_text_empty_returns_empty() -> None:
    assert chunk_text("") == []


def test_chunk_text_whitespace_only_returns_empty() -> None:
    assert chunk_text("   \n\n   \n\n   ") == []


def test_chunk_text_short_content_returns_single_chunk() -> None:
    content = "hello world"
    result = chunk_text(content)
    assert result == ["hello world"]


def test_chunk_text_two_short_paragraphs_are_coalesced() -> None:
    # Deux paragraphes courts (< min_chars) → coalescés en 1 chunk
    content = "Paragraphe un.\n\nParagraphe deux."
    result = chunk_text(content)
    assert len(result) == 1
    assert "Paragraphe un." in result[0]
    assert "Paragraphe deux." in result[0]


def test_chunk_text_two_long_paragraphs_split_with_overlap() -> None:
    # Deux paragraphes > max_chars → 2+ chunks avec overlap
    para_a = "A" * 1500
    para_b = "B" * 1500
    content = f"{para_a}\n\n{para_b}"
    result = chunk_text(content, max_chars=2000, min_chars=200, overlap_chars=200)
    assert len(result) >= 2
    # Overlap : le chunk[i+1] doit contenir au moins une partie de la fin de chunk[i]
    for i in range(1, len(result)):
        # Au moins overlap_chars chars en commun en fin/début
        assert any(result[i].startswith(result[i - 1][-k:]) for k in range(50, 201))


def test_chunk_text_single_giant_paragraph_split_on_separator() -> None:
    # 1 paragraphe géant (3000 chars) → split sur séparateur naturel
    content = "Phrase courte. " * 200  # ~3000 chars, plein de ". "
    result = chunk_text(content, max_chars=2000, min_chars=200, overlap_chars=200)
    assert len(result) >= 2
    # Chaque chunk <= max_chars + overlap_chars
    for chunk in result:
        assert len(chunk) <= 2200


def test_chunk_text_code_no_paragraph_splits_on_newline() -> None:
    # Code sans `\n\n` → fallback sur `\n`
    content = "\n".join([f"line {i}" for i in range(500)])  # ~3500 chars
    result = chunk_text(content, max_chars=2000)
    assert len(result) >= 2


def test_chunk_text_overlap_too_large_raises() -> None:
    with pytest.raises(ValueError, match="overlap"):
        chunk_text("hello", max_chars=100, overlap_chars=150)


def test_chunk_text_strips_outer_whitespace() -> None:
    content = "\n\n   hello   \n\n"
    result = chunk_text(content)
    assert result == ["hello"]


def test_chunk_text_preserves_content_when_short() -> None:
    content = "Multi-line\ncontent\nwith newlines"
    result = chunk_text(content)
    # Sous min_chars → 1 chunk avec contenu intact (modulo strip outer ws)
    assert len(result) == 1
    assert result[0] == content
