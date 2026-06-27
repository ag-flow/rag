from __future__ import annotations

import pytest

from rag.indexer.chunking.code_parser import (
    CodeParser,
    UnsupportedLanguageError,
)

_PY = "import os\n\ndef foo(x):\n    return x + 1\n\nclass A:\n    def m(self):\n        return 2\n"


class TestCodeParser:
    def test_unsupported_language_raises(self) -> None:
        with pytest.raises(UnsupportedLanguageError):
            CodeParser("klingon")

    def test_top_level_named_nodes(self) -> None:
        root = CodeParser("python").parse(_PY)
        kinds = [(c.kind, c.name) for c in root.named_children]
        assert ("function_definition", "foo") in kinds
        assert ("class_definition", "A") in kinds

    def test_node_text_and_lines(self) -> None:
        root = CodeParser("python").parse(_PY)
        foo = next(c for c in root.named_children if c.name == "foo")
        assert foo.text.startswith("def foo(x):")
        assert "return x + 1" in foo.text
        assert foo.start_line == 2
        assert foo.end_line == 3

    def test_nested_children_for_class_methods(self) -> None:
        root = CodeParser("python").parse(_PY)
        cls = next(c for c in root.named_children if c.name == "A")
        method_names = {
            d.name for d in _descendants(cls) if d.kind == "function_definition"
        }
        assert "m" in method_names

    def test_name_none_when_no_name_field(self) -> None:
        root = CodeParser("python").parse("x = 1\n")
        # expression_statement / assignment n'a pas de field 'name'
        assert all(c.name is None for c in root.named_children)

    def test_has_error_on_broken_source(self) -> None:
        root = CodeParser("python").parse("def broken(:\n")
        assert root.has_error is True

    def test_clean_source_no_error(self) -> None:
        root = CodeParser("python").parse(_PY)
        assert root.has_error is False


def _descendants(node) -> list:
    out = []
    for c in node.named_children:
        out.append(c)
        out.extend(_descendants(c))
    return out
