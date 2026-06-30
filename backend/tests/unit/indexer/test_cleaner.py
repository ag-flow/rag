from __future__ import annotations

from unittest.mock import MagicMock

from rag.indexer.chunking.cleaner import CleaningChunkerWrapper, clean_content_text
from rag.indexer.chunking.structured import ChunkedDocument


class TestCleanContentText:
    def test_nfkc_normalisation(self):
        # fi ligature -> fi
        assert clean_content_text("\ufb01le") == "file"

    def test_crlf_to_lf(self):
        assert clean_content_text("a\r\nb") == "a\nb"

    def test_cr_to_lf(self):
        assert clean_content_text("a\rb") == "a\nb"

    def test_trailing_whitespace_removed(self):
        assert clean_content_text("hello   \nworld\t\n") == "hello\nworld\n"

    def test_max_two_blank_lines(self):
        assert clean_content_text("a\n\n\n\n\nb") == "a\n\nb"

    def test_three_blanks_become_two(self):
        assert clean_content_text("a\n\n\n\nb") == "a\n\nb"

    def test_two_blanks_unchanged(self):
        assert clean_content_text("a\n\nb") == "a\n\nb"

    def test_code_indentation_preserved(self):
        code = "def foo():\n    return 42\n"
        assert clean_content_text(code) == code

    def test_empty_string_unchanged(self):
        assert clean_content_text("") == ""

    def test_idempotent(self):
        text = "hello\nworld\n\nfoo\n"
        assert clean_content_text(clean_content_text(text)) == clean_content_text(text)

    def test_non_breaking_space_normalized(self):
        # U+00A0 non-breaking space -> espace normal via NFKC
        nbsp = "\u00a0"
        result = clean_content_text(f"hello{nbsp}world")
        assert nbsp not in result

    def test_mixed_noise(self):
        dirty = "Title   \r\n\r\nBody\n\n\n\nFoo\t\n"
        result = clean_content_text(dirty)
        assert "\r" not in result
        assert "\n\n\n" not in result
        assert "   \n" not in result
        assert "\t\n" not in result


class TestCleaningChunkerWrapper:
    def test_delegates_to_inner_with_cleaned_content(self):
        inner = MagicMock()
        inner.chunk.return_value = ChunkedDocument(parents=[], children=[])
        wrapper = CleaningChunkerWrapper(inner)

        dirty = "hello   \n\n\n\nworld"
        wrapper.chunk(dirty)

        called_with = inner.chunk.call_args[0][0]
        assert "\n\n\n" not in called_with
        assert "   \n" not in called_with

    def test_returns_inner_result(self):
        from rag.indexer.chunking.structured import ChildChunk, ParentSection

        expected = ChunkedDocument(
            parents=[ParentSection(section_key="k", content="c")],
            children=[ChildChunk(embed_text="e", parent_key="k")],
        )
        inner = MagicMock()
        inner.chunk.return_value = expected
        wrapper = CleaningChunkerWrapper(inner)

        result = wrapper.chunk("text")
        assert result is expected
