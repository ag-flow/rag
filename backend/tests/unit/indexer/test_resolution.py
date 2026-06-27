from __future__ import annotations

import pytest

from rag.indexer.chunking.resolution import RoutingConfig, merge_maps, resolve_strategy_name


def _routing() -> RoutingConfig:
    return RoutingConfig(
        extension_categories={".md": "prose", ".py": "code", ".csv": "table"},
        category_strategies={
            "prose": "markdown-deep",
            "code": "code-aware",
            "table": "table",
        },
    )


class TestMergeMaps:
    def test_workspace_overrides_global_key_by_key(self) -> None:
        merged = merge_maps({".md": "prose", ".py": "code"}, {".py": "table"})
        assert merged == {".md": "prose", ".py": "table"}

    def test_global_kept_when_workspace_absent(self) -> None:
        assert merge_maps({".md": "prose"}, {}) == {".md": "prose"}

    def test_workspace_adds_new_key(self) -> None:
        assert merge_maps({}, {".rs": "code"}) == {".rs": "code"}


class TestResolve:
    def test_override_wins_over_routing(self) -> None:
        name = resolve_strategy_name(path="x.md", override="table", routing=_routing())
        assert name == "table"

    def test_override_wins_even_without_path(self) -> None:
        name = resolve_strategy_name(path=None, override="code-aware", routing=_routing())
        assert name == "code-aware"

    def test_extension_routed_to_category_strategy(self) -> None:
        assert (
            resolve_strategy_name(path="docs/guide.md", override=None, routing=_routing())
            == "markdown-deep"
        )
        assert (
            resolve_strategy_name(path="src/app.py", override=None, routing=_routing())
            == "code-aware"
        )
        assert (
            resolve_strategy_name(path="data/x.csv", override=None, routing=_routing()) == "table"
        )

    def test_extension_case_insensitive(self) -> None:
        assert (
            resolve_strategy_name(path="README.MD", override=None, routing=_routing())
            == "markdown-deep"
        )

    def test_unmapped_extension_uses_default_category(self) -> None:
        assert (
            resolve_strategy_name(path="weird.xyz", override=None, routing=_routing())
            == "markdown-deep"
        )

    def test_no_extension_uses_default(self) -> None:
        assert (
            resolve_strategy_name(path="Makefile", override=None, routing=_routing())
            == "markdown-deep"
        )

    def test_none_path_uses_default(self) -> None:
        assert (
            resolve_strategy_name(path=None, override=None, routing=_routing()) == "markdown-deep"
        )

    def test_category_without_strategy_falls_back_to_default_category(self) -> None:
        routing = RoutingConfig(
            extension_categories={".py": "code"},
            category_strategies={"prose": "markdown-deep"},  # 'code' non mappé
        )
        assert resolve_strategy_name(path="a.py", override=None, routing=routing) == "markdown-deep"

    def test_missing_default_category_strategy_raises(self) -> None:
        routing = RoutingConfig(extension_categories={}, category_strategies={})
        with pytest.raises(ValueError, match="default category"):
            resolve_strategy_name(path="a.md", override=None, routing=routing)
