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


def test_make_chunker_markdown_returns_markdown_chunker() -> None:
    from rag.indexer.chunking import MarkdownChunker

    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={"heading_levels": [1, 2]},
    )
    assert isinstance(chunker, MarkdownChunker)


def test_make_chunker_markdown_default_heading_levels() -> None:
    """extras={} -> heading_levels=(1,2) par defaut."""
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={},
    )
    # Comportement observable : H1 + H2 doivent split, H3 pas
    content = "# A\n\nAlpha.\n\n## B\n\nBravo.\n\n### C\n\nCharlie."
    result = chunker.chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "A" in titles
    assert "B" in titles
    assert "C" not in titles  # H3 absorbe dans B


def test_make_chunker_markdown_custom_heading_levels() -> None:
    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={"heading_levels": [1, 2, 3]},
    )
    content = "# A\n\nAlpha.\n\n## B\n\nBravo.\n\n### C\n\nCharlie."
    result = chunker.chunk(content)
    titles = [c.metadata["section_title"] for c in result]
    assert "C" in titles  # H3 doit declencher un split


def test_make_chunker_markdown_rejects_unknown_extras_key() -> None:
    with pytest.raises(ValueError, match="unknown extras keys"):
        make_chunker(
            strategy="markdown",
            max_chars=2000,
            min_chars=200,
            overlap_chars=200,
            extras={"foo": "bar"},
        )


def test_make_chunker_markdown_immutable_levels() -> None:
    """heading_levels est stocke en tuple (immutable)."""
    from rag.indexer.chunking.markdown import MarkdownChunker

    chunker = make_chunker(
        strategy="markdown",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={"heading_levels": [1, 2]},
    )
    assert isinstance(chunker, MarkdownChunker)
    # Acces au champ prive pour verifier le type immutable
    assert isinstance(chunker._heading_levels, tuple)
