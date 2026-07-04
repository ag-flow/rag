from __future__ import annotations

from unittest.mock import MagicMock

from rag.indexer.chunking.cleaner import (
    CleaningChunkerWrapper,
    CleaningOptions,
    clean_content_text,
    strip_boilerplate_lines,
    strip_decorative_separators,
    strip_html_tags,
)
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

    def test_explicit_options_applied(self):
        inner = MagicMock()
        inner.chunk.return_value = ChunkedDocument(parents=[], children=[])
        opts = CleaningOptions(strip_html=True)
        wrapper = CleaningChunkerWrapper(inner, opts)

        wrapper.chunk("<b>hello</b>")
        called_with = inner.chunk.call_args[0][0]
        assert "<b>" not in called_with
        assert "hello" in called_with

    def test_all_options_disabled_passes_content_unchanged(self):
        inner = MagicMock()
        inner.chunk.return_value = ChunkedDocument(parents=[], children=[])
        opts = CleaningOptions()  # tout à False
        wrapper = CleaningChunkerWrapper(inner, opts)

        original = "<b>text</b>\n---\n# Auto-generated\nreal"
        wrapper.chunk(original)
        assert inner.chunk.call_args[0][0] == original


class TestStripDecorativeSeparators:
    def test_removes_triple_dash_after_blank(self):
        # --- précédé d'une ligne vide = séparateur horizontal, pas un underline setext
        assert "---" not in strip_decorative_separators("a\n\n---\n\nb")

    def test_removes_triple_equal_after_blank(self):
        assert "===" not in strip_decorative_separators("a\n\n===\n\nb")

    def test_removes_triple_star(self):
        assert "***" not in strip_decorative_separators("before\n\n***\n\nafter")

    def test_removes_triple_tilde(self):
        assert "~~~" not in strip_decorative_separators("before\n\n~~~\n\nafter")

    def test_removes_long_underscore(self):
        assert "___" not in strip_decorative_separators("before\n\n___\n\nafter")

    def test_preserves_setext_h1_underline(self):
        text = "Title\n=====\n\nContent"
        result = strip_decorative_separators(text)
        assert "=====" in result

    def test_preserves_setext_h2_underline(self):
        text = "Subtitle\n--------\n\nContent"
        result = strip_decorative_separators(text)
        assert "--------" in result

    def test_removes_standalone_dash_after_blank(self):
        result = strip_decorative_separators("\n---\n")
        assert "---" not in result

    def test_content_text_preserved(self):
        result = strip_decorative_separators("before\n---\nafter")
        assert "before" in result
        assert "after" in result

    def test_idempotent(self):
        text = "a\n\nb\n\nc"
        once = strip_decorative_separators(text)
        assert strip_decorative_separators(once) == once

    def test_empty_string(self):
        assert strip_decorative_separators("") == ""


class TestStripHtmlTags:
    def test_strips_opening_tag(self):
        assert "<b>" not in strip_html_tags("hello <b>world</b>")

    def test_strips_closing_tag(self):
        assert "</b>" not in strip_html_tags("<b>text</b>")

    def test_keeps_text_content(self):
        assert "world" in strip_html_tags("<p>world</p>")

    def test_replaces_amp_entity(self):
        assert strip_html_tags("a &amp; b") == "a & b"

    def test_replaces_lt_gt_entities_and_strips_resulting_tag(self):
        # &lt;em&gt;text&lt;/em&gt; → décodé en <em>text</em> → stripé → text
        assert strip_html_tags("&lt;em&gt;bold&lt;/em&gt;") == "bold"

    def test_replaces_nbsp_with_space(self):
        assert strip_html_tags("a&nbsp;b") == "a b"

    def test_replaces_quot_entity(self):
        assert strip_html_tags("&quot;hello&quot;") == '"hello"'

    def test_strips_numeric_decimal_entity(self):
        assert "&#123;" not in strip_html_tags("a&#123;b")

    def test_strips_numeric_hex_entity(self):
        assert "&#x7B;" not in strip_html_tags("a&#x7B;b")

    def test_strips_self_closing_tag(self):
        assert "<br/>" not in strip_html_tags("line<br/>break")

    def test_empty_string_unchanged(self):
        assert strip_html_tags("") == ""

    def test_no_html_unchanged(self):
        text = "plain text without html"
        assert strip_html_tags(text) == text


class TestStripBoilerplateLines:
    def test_strips_auto_generated(self):
        result = strip_boilerplate_lines("# Auto-generated file\ncode here")
        assert "Auto-generated" not in result
        assert "code here" in result

    def test_strips_do_not_edit(self):
        result = strip_boilerplate_lines("// Do not edit this file\ncode")
        assert "Do not edit" not in result
        assert "code" in result

    def test_strips_spdx_license(self):
        result = strip_boilerplate_lines("// SPDX-License-Identifier: MIT\ncode")
        assert "SPDX" not in result

    def test_strips_spdx_copyright(self):
        result = strip_boilerplate_lines("// SPDX-FileCopyrightText: 2024 Foo\ncode")
        assert "SPDX" not in result

    def test_strips_copyright_c(self):
        result = strip_boilerplate_lines("// Copyright (c) 2024 Foo Corp\ncode")
        assert "Copyright" not in result

    def test_strips_all_rights_reserved(self):
        result = strip_boilerplate_lines("// All rights reserved.\ncode")
        assert "All rights reserved" not in result

    def test_strips_generated_by(self):
        result = strip_boilerplate_lines("# Generated by protoc v3.21\ncode")
        assert "Generated by" not in result

    def test_preserves_normal_lines(self):
        text = "def foo():\n    return 42"
        assert strip_boilerplate_lines(text) == text

    def test_strips_repeated_non_indented_lines(self):
        footer = "MyCompany Footer Line"
        lines = ["content"] + [footer] * 5 + ["more content"]
        result = strip_boilerplate_lines("\n".join(lines))
        assert footer not in result
        assert "content" in result

    def test_preserves_repeated_indented_lines(self):
        indented = "    return None"
        lines = [indented] * 6 + ["real content"]
        result = strip_boilerplate_lines("\n".join(lines))
        assert "return None" in result

    def test_preserves_repeated_short_lines(self):
        short = "hi"
        lines = [short] * 10 + ["real content"]
        result = strip_boilerplate_lines("\n".join(lines))
        assert "real content" in result

    def test_case_insensitive(self):
        result = strip_boilerplate_lines("AUTO-GENERATED\ncode")
        assert "AUTO-GENERATED" not in result


class TestCleaningOptions:
    def test_all_false_any_enabled_false(self):
        assert not CleaningOptions().any_enabled

    def test_clean_content_true_any_enabled(self):
        assert CleaningOptions(clean_content=True).any_enabled

    def test_strip_separators_true_any_enabled(self):
        assert CleaningOptions(strip_separators=True).any_enabled

    def test_strip_boilerplate_true_any_enabled(self):
        assert CleaningOptions(strip_boilerplate=True).any_enabled

    def test_strip_html_true_any_enabled(self):
        assert CleaningOptions(strip_html=True).any_enabled
