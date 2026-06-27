from __future__ import annotations

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import ChunkedDocument
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=1.0)


def _chunker(
    *,
    target: int = 2000,
    floor: int = 0,
    overlap: int = 0,
    hard: int = 8000,
    depth: int = -1,
    heading_levels: tuple[int, ...] = (1, 2),
) -> MarkdownDeepChunker:
    return MarkdownDeepChunker(
        estimator=_EST,
        bounds=TokenBounds(
            child_target_tokens=target,
            floor_tokens=floor,
            overlap_tokens=overlap,
            hard_ceiling_tokens=hard,
        ),
        breadcrumb_depth=depth,
        heading_levels=heading_levels,
    )


class TestStructure:
    def test_empty_content_returns_empty_document(self) -> None:
        doc = _chunker().chunk("   \n  ")
        assert doc == ChunkedDocument(parents=[], children=[])

    def test_single_section_one_parent_children_reference_it(self) -> None:
        doc = _chunker().chunk("# Guide\n\nIntro paragraph.")
        assert len(doc.parents) == 1
        parent = doc.parents[0]
        assert parent.section_key == "Guide"
        assert "# Guide" in parent.content
        assert doc.children
        assert all(c.parent_key == parent.section_key for c in doc.children)

    def test_parent_content_has_no_breadcrumb_but_children_do(self) -> None:
        doc = _chunker(depth=-1).chunk("# Guide\n\nIntro paragraph.")
        assert not doc.parents[0].content.startswith("Guide\n\n")
        assert all(c.embed_text.startswith("Guide\n\n") for c in doc.children)

    def test_nested_headings_breadcrumb_includes_own_title(self) -> None:
        md = "# Guide\n\nIntro.\n\n## Install\n\nInstall body."
        doc = _chunker(depth=-1).chunk(md)
        keys = {p.section_key for p in doc.parents}
        assert keys == {"Guide", "Guide/Install"}
        install_children = [c for c in doc.children if c.parent_key == "Guide/Install"]
        assert install_children
        assert all(c.embed_text.startswith("Guide > Install\n\n") for c in install_children)

    def test_preamble_becomes_root_parent(self) -> None:
        md = "Preamble text before any heading.\n\n# Guide\n\nBody."
        doc = _chunker().chunk(md)
        root = [p for p in doc.parents if p.metadata["heading_level"] == 0]
        assert len(root) == 1
        assert "Preamble text" in root[0].content

    def test_no_headings_single_root_parent(self) -> None:
        doc = _chunker().chunk("Just prose.\n\nSecond paragraph.")
        assert len(doc.parents) == 1
        assert doc.parents[0].section_key == "(root)"
        assert len(doc.children) >= 1

    def test_duplicate_titles_get_distinct_keys(self) -> None:
        md = "# Notes\n\nA.\n\n# Notes\n\nB."
        doc = _chunker().chunk(md)
        keys = [p.section_key for p in doc.parents]
        assert keys == ["Notes", "Notes#2"]


class TestBounds:
    def test_big_section_splits_into_multiple_children(self) -> None:
        body = " ".join(f"word{i:03d}" for i in range(200))  # ~1400 chars
        doc = _chunker(target=200, overlap=0, hard=8000, depth=0).chunk(f"# S\n\n{body}")
        assert len(doc.children) > 1
        for child in doc.children:
            assert _EST.estimate(child.embed_text) <= 8000

    def test_code_fence_kept_as_single_child(self) -> None:
        md = "# Code\n\n```python\na = 1\n\nb = 2\n```\n"
        doc = _chunker(depth=0).chunk(md)
        fence_children = [c for c in doc.children if "```python" in c.embed_text]
        assert len(fence_children) == 1
        # la fence n'est pas shreddée sur sa ligne vide interne
        assert "a = 1" in fence_children[0].embed_text
        assert "b = 2" in fence_children[0].embed_text

    def test_large_code_fence_not_shredded_by_ceiling(self) -> None:
        # T1.4 : une fence > child_target reste UN seul child (pas de word-shred).
        lines = "\n".join(f"line_{i:03d} = {i}" for i in range(60))
        md = f"# Code\n\n```python\n{lines}\n```\n"
        doc = _chunker(target=50, overlap=0, hard=8000, depth=0).chunk(md)
        fence_children = [c for c in doc.children if "```python" in c.embed_text]
        assert len(fence_children) == 1
        assert "line_000 = 0" in fence_children[0].embed_text
        assert "line_059 = 59" in fence_children[0].embed_text

    def test_oversized_atomic_unit_raises(self) -> None:
        giant = "x" * 100  # 1 mot insécable de 100 tokens
        chunker = _chunker(target=20, overlap=0, hard=50, depth=0)
        try:
            chunker.chunk(f"# S\n\n{giant}")
        except ChunkTooLargeError as exc:
            assert exc.estimated_tokens == 100
        else:
            raise AssertionError("ChunkTooLargeError attendu")


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        md = "# A\n\nx.\n\n## B\n\ny."
        assert _chunker().chunk(md) == _chunker().chunk(md)
