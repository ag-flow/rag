from __future__ import annotations

from itertools import pairwise

import pytest

from rag.indexer.chunking.markdown_regions import MarkdownRegionParser
from rag.indexer.chunking.region_registry import available_parsers, get_region_parser
from rag.indexer.chunking.regions import REGION_TYPES, Region

_PARSER = MarkdownRegionParser()


def _types(regions: list[Region]) -> list[str]:
    return [r.type for r in regions]


class TestProtocolConformance:
    def test_slug_and_region_types(self) -> None:
        assert _PARSER.slug == "markdown"
        assert _PARSER.region_types == REGION_TYPES

    def test_registry_resolves_markdown(self) -> None:
        assert isinstance(get_region_parser("markdown"), MarkdownRegionParser)
        assert available_parsers() == frozenset({"markdown"})

    def test_registry_rejects_unknown_slug(self) -> None:
        with pytest.raises(ValueError, match="html"):
            get_region_parser("html")


class TestBasicSegmentation:
    def test_empty_document_yields_no_region(self) -> None:
        assert _PARSER.parse("") == []

    def test_document_without_heading_is_prose_with_empty_path(self) -> None:
        regions = _PARSER.parse("juste du texte\nsur deux lignes\n")
        assert _types(regions) == ["prose"]
        assert regions[0].heading_path == []

    def test_fence_with_info_string_is_qualified(self) -> None:
        doc = "intro\n\n```python\nprint('x')\n```\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose", "code_fence"]
        assert regions[1].qualifier == "python"

    def test_fence_with_empty_info_string_has_no_qualifier(self) -> None:
        regions = _PARSER.parse("```\nraw\n```\n")
        assert _types(regions) == ["code_fence"]
        assert regions[0].qualifier is None

    def test_mermaid_is_a_qualified_code_fence_not_a_type(self) -> None:
        regions = _PARSER.parse("```mermaid\ngraph TD\n```\n")
        assert (regions[0].type, regions[0].qualifier) == ("code_fence", "mermaid")


class TestHeadingPath:
    def test_fence_under_nested_h2_gets_full_breadcrumb(self) -> None:
        doc = "# Guide\n\n## Installation\n\n```mermaid\ngraph TD\n```\n"
        regions = _PARSER.parse(doc)
        fence = next(r for r in regions if r.type == "code_fence")
        assert fence.heading_path == ["Guide", "Installation"]

    def test_sibling_h2_replaces_previous_in_breadcrumb(self) -> None:
        doc = "# Guide\n\n## Un\n\n## Deux\n\n```sh\nls\n```\n"
        fence = next(r for r in _PARSER.parse(doc) if r.type == "code_fence")
        assert fence.heading_path == ["Guide", "Deux"]

    def test_prose_region_path_is_snapshot_at_opening(self) -> None:
        doc = "# Guide\n\ntexte\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose"]
        assert regions[0].heading_path == []


class TestFrontmatter:
    def test_yaml_head_is_frontmatter_region(self) -> None:
        doc = "---\ntitle: Doc\n---\n\n# Guide\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["frontmatter", "prose"]
        assert regions[0].content == "---\ntitle: Doc\n---\n"

    def test_unclosed_head_marker_is_not_frontmatter(self) -> None:
        regions = _PARSER.parse("---\ntitle: Doc\n")
        assert _types(regions) == ["prose"]

    def test_delimiter_later_in_document_is_not_frontmatter(self) -> None:
        regions = _PARSER.parse("intro\n\n---\ntexte\n---\n")
        assert _types(regions) == ["prose"]


class TestTable:
    def test_pipe_table_is_a_table_region(self) -> None:
        doc = "avant\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\naprès\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose", "table", "prose"]
        assert regions[1].content == "| a | b |\n| --- | --- |\n| 1 | 2 |\n"

    def test_table_at_end_of_file(self) -> None:
        doc = "texte\n\n| a |\n| --- |\n| 1 |"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose", "table"]
        assert regions[-1].content.endswith("| 1 |")

    def test_pipes_without_delimiter_row_stay_prose(self) -> None:
        regions = _PARSER.parse("a | b\nc | d\n")
        assert _types(regions) == ["prose"]


class TestHtmlBlock:
    def test_html_block_is_typed(self) -> None:
        doc = 'texte\n\n<div class="note">\ncontenu\n</div>\n\nsuite\n'
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose", "html_block", "prose"]
        assert regions[1].content.startswith("<div")

    def test_inline_html_in_paragraph_stays_prose(self) -> None:
        regions = _PARSER.parse("un mot <em>fort</em> ici\n")
        assert _types(regions) == ["prose"]


class TestFenceEdgeCases:
    def test_unclosed_fence_runs_to_end_of_file(self) -> None:
        doc = "intro\n\n```python\nprint('x')\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["prose", "code_fence"]
        assert regions[1].end_line == 4

    def test_fence_indented_in_list_is_detected(self) -> None:
        doc = "- item\n  ```sh\n  ls\n  ```\n- suite\n"
        regions = _PARSER.parse(doc)
        assert "code_fence" in _types(regions)
        fence = next(r for r in regions if r.type == "code_fence")
        assert fence.qualifier == "sh"

    def test_longer_inner_fence_marker_does_not_close_outer(self) -> None:
        doc = "````md\n```\ninner\n```\n````\n"
        regions = _PARSER.parse(doc)
        assert _types(regions) == ["code_fence"]


class TestReconstruction:
    @pytest.mark.parametrize(
        "doc",
        [
            "",
            "\n\n",
            "juste du texte\n",
            "sans newline finale",
            "---\ntitle: X\n---\n\n# T\n\n```python\ncode\n```\n\n"
            "| a |\n| - |\n| 1 |\n\n<div>\nx\n</div>\n\nfin\n",
            "# T\n\n```py\nouvert sans fin\n",
            "- liste\n  ```sh\n  ls\n  ```\ntexte | pipe\n",
        ],
    )
    def test_concatenation_restores_source(self, doc: str) -> None:
        assert "".join(r.content for r in _PARSER.parse(doc)) == doc

    def test_regions_are_contiguous_without_overlap(self) -> None:
        doc = "---\na: 1\n---\nintro\n\n```sh\nls\n```\n\n| a |\n| - |\n\nfin\n"
        regions = _PARSER.parse(doc)
        assert regions[0].start_line == 1
        for previous, current in pairwise(regions):
            assert current.start_line == previous.end_line + 1
        assert regions[-1].end_line == doc.count("\n")
