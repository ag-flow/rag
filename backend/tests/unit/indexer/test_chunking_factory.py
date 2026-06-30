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


# ── Tests du paramètre clean_content dans make_structured_chunker ────────────


def _make_structured(algo: str, params: dict) -> object:
    from rag.indexer.chunking.structured_factory import make_structured_chunker
    from rag.indexer.chunking.tokens import HeuristicTokenEstimator

    return make_structured_chunker(
        algo=algo,
        params=params,
        estimator=HeuristicTokenEstimator(),
        provider_max_input_tokens=8192,
    )


class TestCleanContentParam:
    def test_clean_content_absent_returns_plain_chunker(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("prose", {})
        assert not isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_false_returns_plain_chunker(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("prose", {"clean_content": False})
        assert not isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_prose_returns_wrapper(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("prose", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_code_returns_wrapper(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("code", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_data_returns_wrapper(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("data", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_clean_content_true_table_returns_wrapper(self) -> None:
        from rag.indexer.chunking.cleaner import CleaningChunkerWrapper

        chunker = _make_structured("table", {"clean_content": True})
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_unknown_param_still_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown params"):
            _make_structured("prose", {"typo_param": True})
