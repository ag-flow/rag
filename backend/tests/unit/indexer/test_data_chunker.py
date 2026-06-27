from __future__ import annotations

from rag.indexer.chunking.data_chunker import DataChunker
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import ChunkedDocument
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=1.0)


def _chunker(*, language: str = "json", target: int = 4000, depth: int = -1) -> DataChunker:
    return DataChunker(
        language=language,
        estimator=_EST,
        bounds=TokenBounds(target, 0, 0, 8000),
        breadcrumb_depth=depth,
    )


_JSON = '{\n  "alpha": 1,\n  "beta": {"x": 2},\n  "gamma": [1, 2, 3]\n}\n'
_YAML = "alpha: 1\nbeta:\n  x: 2\ngamma:\n  - 1\n  - 2\n"


class TestJson:
    def test_empty(self) -> None:
        assert _chunker().chunk("  ") == ChunkedDocument(parents=[], children=[])

    def test_top_level_keys_become_units(self) -> None:
        doc = _chunker().chunk(_JSON)
        assert {p.section_key for p in doc.parents} == {"alpha", "beta", "gamma"}

    def test_child_breadcrumb_is_key(self) -> None:
        doc = _chunker(depth=-1).chunk(_JSON)
        beta = [c for c in doc.children if c.parent_key == "beta"]
        assert beta and all(c.embed_text.startswith("beta\n\n") for c in beta)

    def test_children_reference_parents(self) -> None:
        doc = _chunker().chunk(_JSON)
        keys = {p.section_key for p in doc.parents}
        assert all(c.parent_key in keys for c in doc.children)

    def test_top_level_array_falls_back_to_root_unit(self) -> None:
        doc = _chunker().chunk("[1, 2, 3]\n")
        assert [p.section_key for p in doc.parents] == ["(root)"]


class TestYaml:
    def test_top_level_keys(self) -> None:
        doc = _chunker(language="yaml").chunk(_YAML)
        assert {"alpha", "beta", "gamma"} <= {p.section_key for p in doc.parents}


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        assert _chunker().chunk(_JSON) == _chunker().chunk(_JSON)
