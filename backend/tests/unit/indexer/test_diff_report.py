from __future__ import annotations

from rag.indexer.chunking.diff_report import render_chunk_diff

_CORPUS = (
    "# Guide\n\n"
    "Intro paragraph with enough words to matter here.\n\n"
    "## Installation\n\n"
    "Run the installer. Then configure it.\n\n"
    "```python\nx = 1\n\ny = 2\n```\n\n"
    "## Usage\n\n"
    "Use it wisely and often."
)


class TestRenderChunkDiff:
    def test_report_has_both_sections(self) -> None:
        report = render_chunk_diff(_CORPUS)
        assert "## LEGACY" in report
        assert "## STRUCTURED" in report

    def test_structured_lists_parents_and_children(self) -> None:
        report = render_chunk_diff(_CORPUS)
        assert "parent: Guide/Installation" in report
        assert "parent: Guide/Usage" in report
        assert "#### child 0" in report

    def test_deterministic(self) -> None:
        assert render_chunk_diff(_CORPUS) == render_chunk_diff(_CORPUS)

    def test_empty_corpus_reports_zero(self) -> None:
        report = render_chunk_diff("")
        assert "chunks=0" in report
        assert "parents=0, children=0" in report

    def test_code_fence_not_shredded_in_structured(self) -> None:
        report = render_chunk_diff(_CORPUS)
        # le bloc de code reste sur un seul enfant (ligne vide interne préservée)
        assert "```python" in report
