from __future__ import annotations

from rag.indexer.chunking.code_chunker import CodeChunker
from rag.indexer.chunking.languages import language_for_path
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=4.0)


def _make(algo: str, language: str | None):
    return make_structured_chunker(
        algo=algo,
        params={"child_target_tokens": 256},
        estimator=_EST,
        provider_max_input_tokens=8192,
        language=language,
    )


class TestLanguageMap:
    def test_known_extensions(self) -> None:
        assert language_for_path("src/app.py") == "python"
        assert language_for_path("a/b.ts") == "typescript"
        assert language_for_path("x.go") == "go"
        assert language_for_path("DIR/Main.JAVA") == "java"

    def test_unknown_extension_returns_none(self) -> None:
        assert language_for_path("notes.md") is None
        assert language_for_path("Makefile") is None
        assert language_for_path(None) is None


class TestCodeFactoryDispatch:
    def test_code_algo_with_supported_language(self) -> None:
        assert isinstance(_make("code", "python"), CodeChunker)

    def test_code_algo_unsupported_language_falls_back_to_prose(self) -> None:
        assert isinstance(_make("code", "klingon"), MarkdownDeepChunker)

    def test_code_algo_without_language_falls_back_to_prose(self) -> None:
        assert isinstance(_make("code", None), MarkdownDeepChunker)

    def test_code_rejects_heading_levels_param(self) -> None:
        import pytest

        with pytest.raises(ValueError, match="unknown"):
            make_structured_chunker(
                algo="code",
                params={"heading_levels": [1, 2]},
                estimator=_EST,
                provider_max_input_tokens=8192,
                language="python",
            )
