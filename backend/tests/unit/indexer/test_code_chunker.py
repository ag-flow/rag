from __future__ import annotations

from rag.indexer.chunking.code_chunker import CodeChunker
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import ChunkedDocument
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=1.0)

_PY = "import os\n\ndef foo(x):\n    return x + 1\n\nclass A:\n    def m(self):\n        return 2\n"


def _chunker(
    *,
    language: str = "python",
    target: int = 4000,
    floor: int = 0,
    overlap: int = 0,
    hard: int = 8000,
    depth: int = -1,
) -> CodeChunker:
    return CodeChunker(
        language=language,
        estimator=_EST,
        bounds=TokenBounds(
            child_target_tokens=target,
            floor_tokens=floor,
            overlap_tokens=overlap,
            hard_ceiling_tokens=hard,
        ),
        breadcrumb_depth=depth,
    )


class TestStructure:
    def test_empty_returns_empty(self) -> None:
        assert _chunker().chunk("   ") == ChunkedDocument(parents=[], children=[])

    def test_python_units(self) -> None:
        doc = _chunker().chunk(_PY)
        keys = {p.section_key for p in doc.parents}
        assert "(module)" in keys  # imports module-level
        assert "foo" in keys
        assert "A" in keys
        assert "A/m" in keys

    def test_children_reference_existing_parents(self) -> None:
        doc = _chunker().chunk(_PY)
        keys = {p.section_key for p in doc.parents}
        assert all(c.parent_key in keys for c in doc.children)

    def test_method_breadcrumb_uses_scope(self) -> None:
        doc = _chunker(depth=-1).chunk(_PY)
        m_children = [c for c in doc.children if c.parent_key == "A/m"]
        assert m_children
        assert all(c.embed_text.startswith("A > m\n\n") for c in m_children)

    def test_class_shell_elides_method_bodies(self) -> None:
        doc = _chunker().chunk(_PY)
        shell = next(p for p in doc.parents if p.section_key == "A")
        assert "class A:" in shell.content
        assert "… m" in shell.content  # corps de méthode élidé
        assert "return 2" not in shell.content  # pas de duplication du corps


class TestBounds:
    def test_large_function_splits_into_multiple_children(self) -> None:
        body = "\n".join(f"    a{i} = value_{i}" for i in range(120))
        doc = _chunker(target=120, overlap=0).chunk(f"def big():\n{body}\n")
        big_children = [c for c in doc.children if c.parent_key == "big"]
        assert len(big_children) > 1
        for child in doc.children:
            assert _EST.estimate(child.embed_text) <= 8000


class TestLanguages:
    def test_go_top_level_funcs(self) -> None:
        go = "package main\n\nfunc Foo() {\n\treturn\n}\n\nfunc Bar() {}\n"
        doc = _chunker(language="go").chunk(go)
        keys = {p.section_key for p in doc.parents}
        assert {"Foo", "Bar"} <= keys

    def test_unconfigured_language_best_effort(self) -> None:
        # ruby n'est pas dans la config curée → mode générique (named-with-name)
        ruby = "def greet\n  puts 'hi'\nend\n"
        doc = _chunker(language="ruby").chunk(ruby)
        assert doc.parents  # produit au moins une unité, pas de crash


class TestDeterminism:
    def test_same_input_same_output(self) -> None:
        assert _chunker().chunk(_PY) == _chunker().chunk(_PY)
