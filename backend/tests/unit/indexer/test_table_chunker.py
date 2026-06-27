from __future__ import annotations

import pytest

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import ChunkedDocument
from rag.indexer.chunking.table import TableChunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=1.0)


def _chunker(*, target: int = 8000, hard: int = 8000, max_rows: int = 50) -> TableChunker:
    return TableChunker(
        estimator=_EST,
        bounds=TokenBounds(
            child_target_tokens=target,
            floor_tokens=0,
            overlap_tokens=0,
            hard_ceiling_tokens=hard,
        ),
        max_rows_per_chunk=max_rows,
    )


_MD = "| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |"
_CSV = "name,age\nalice,30\nbob,25\ncarol,41"


class TestStructure:
    def test_empty_returns_empty(self) -> None:
        assert _chunker().chunk("  \n ") == ChunkedDocument(parents=[], children=[])

    def test_single_parent_holds_full_table(self) -> None:
        doc = _chunker().chunk(_MD)
        assert len(doc.parents) == 1
        assert doc.parents[0].content == _MD
        assert all(c.parent_key == doc.parents[0].section_key for c in doc.children)

    def test_markdown_header_and_separator_repeated_in_each_child(self) -> None:
        doc = _chunker(max_rows=1).chunk(_MD)
        assert len(doc.children) == 3  # 3 data rows
        for child in doc.children:
            assert child.embed_text.startswith("| a | b |\n|---|---|")

    def test_csv_header_repeated_in_each_child(self) -> None:
        doc = _chunker(max_rows=1).chunk(_CSV)
        assert len(doc.children) == 3  # 3 data rows
        for child in doc.children:
            assert child.embed_text.startswith("name,age\n")

    def test_header_only_no_rows_yields_one_header_child(self) -> None:
        doc = _chunker().chunk("name,age")
        assert len(doc.children) == 1
        assert doc.children[0].embed_text == "name,age"


class TestGrouping:
    def test_max_rows_per_chunk_respected(self) -> None:
        doc = _chunker(max_rows=2).chunk(_CSV)  # 3 data rows → 2 + 1
        assert len(doc.children) == 2
        assert doc.children[0].embed_text == "name,age\nalice,30\nbob,25"
        assert doc.children[1].embed_text == "name,age\ncarol,41"

    def test_token_target_flushes_before_max_rows(self) -> None:
        # target serré → 1 ligne par child malgré max_rows=10
        doc = _chunker(target=20, hard=8000, max_rows=10).chunk(_CSV)
        assert len(doc.children) == 3


class TestHardGuard:
    def test_single_row_over_hard_ceiling_raises(self) -> None:
        big_row = "x" * 100
        chunker = _chunker(target=30, hard=40, max_rows=10)
        with pytest.raises(ChunkTooLargeError):
            chunker.chunk(f"h\n{big_row}")


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        assert _chunker().chunk(_MD) == _chunker().chunk(_MD)
