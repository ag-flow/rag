from __future__ import annotations

import dataclasses

import pytest

from rag.indexer.chunking.regions import REGION_TYPES, Region


def _region(**overrides: object) -> Region:
    base: dict[str, object] = {
        "type": "prose",
        "qualifier": None,
        "content": "texte",
        "heading_path": [],
        "start_line": 1,
        "end_line": 1,
    }
    base.update(overrides)
    return Region(**base)  # type: ignore[arg-type]


class TestRegionModel:
    def test_region_is_frozen(self) -> None:
        region = _region()
        with pytest.raises(dataclasses.FrozenInstanceError):
            region.content = "autre"  # type: ignore[misc]

    def test_all_declared_types_are_accepted(self) -> None:
        for region_type in REGION_TYPES:
            assert _region(type=region_type).type == region_type

    def test_unknown_type_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="mermaid"):
            _region(type="mermaid")

    def test_taxonomy_is_the_five_v1_types(self) -> None:
        expected = frozenset({"prose", "code_fence", "table", "frontmatter", "html_block"})
        assert expected == REGION_TYPES

    def test_qualifier_specialises_a_closed_type(self) -> None:
        region = _region(type="code_fence", qualifier="mermaid")
        assert (region.type, region.qualifier) == ("code_fence", "mermaid")

    def test_heading_path_carried_by_region(self) -> None:
        region = _region(heading_path=["Guide", "Installation"])
        assert region.heading_path == ["Guide", "Installation"]
