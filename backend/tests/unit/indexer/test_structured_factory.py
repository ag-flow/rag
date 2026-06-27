from __future__ import annotations

import pytest

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.table import TableChunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=4.0)


class TestDispatch:
    def test_prose_algo_returns_markdown_deep(self) -> None:
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, MarkdownDeepChunker)

    def test_markdown_alias_of_prose(self) -> None:
        chunker = make_structured_chunker(
            algo="markdown",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, MarkdownDeepChunker)

    def test_table_algo_returns_table_chunker(self) -> None:
        chunker = make_structured_chunker(
            algo="table",
            params={"child_target_tokens": 384, "max_rows_per_chunk": 20},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, TableChunker)

    def test_unknown_algo_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown chunking algo"):
            make_structured_chunker(
                algo="quantum",
                params={},
                estimator=_EST,
                provider_max_input_tokens=8192,
            )

    def test_unknown_param_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            make_structured_chunker(
                algo="prose",
                params={"child_target_tokens": 384, "bogus": 1},
                estimator=_EST,
                provider_max_input_tokens=8192,
            )


class TestHardCeilingWiring:
    def test_hard_ceiling_derived_from_provider_limit(self) -> None:
        # provider 10 tokens, safety 0.8 → hard ceiling 8 ; mot insécable de
        # ~25 chars (≈7 tokens à ratio 4)… on force un mot bien au-delà.
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 8, "overlap_tokens": 0, "floor_tokens": 0},
            estimator=_EST,
            provider_max_input_tokens=10,
            safety_factor=0.8,
        )
        giant = "x" * 200  # ≈50 tokens > hard ceiling 8
        with pytest.raises(ChunkTooLargeError):
            chunker.chunk(f"# S\n\n{giant}")

    def test_child_target_clamped_to_hard_ceiling(self) -> None:
        # child_target demandé 384 mais provider minuscule → clamp, pas de crash
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=20,
        )
        doc = chunker.chunk("# S\n\nshort body")
        assert doc.parents


class TestDefaults:
    def test_prose_defaults_applied(self) -> None:
        # sans params → defaults raisonnables, ne lève pas
        chunker = make_structured_chunker(
            algo="prose",
            params={},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        doc = chunker.chunk("# Guide\n\n## Sub\n\nbody")
        assert {p.section_key for p in doc.parents} == {"Guide", "Guide/Sub"}
