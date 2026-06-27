from __future__ import annotations

import pytest

from rag.indexer.chunking.breadcrumb import prepend_breadcrumb, render_breadcrumb


class TestRenderBreadcrumb:
    def test_depth_zero_disabled(self) -> None:
        assert render_breadcrumb(["Guide", "Install"], depth=0) == ""

    def test_full_path_when_depth_minus_one(self) -> None:
        out = render_breadcrumb(["Guide", "Install", "Linux"], depth=-1)
        assert out == "Guide > Install > Linux"

    def test_last_n_levels(self) -> None:
        assert render_breadcrumb(["Guide", "Install", "Linux"], depth=2) == "Install > Linux"

    def test_depth_larger_than_path_returns_full(self) -> None:
        assert render_breadcrumb(["Guide", "Install"], depth=5) == "Guide > Install"

    def test_empty_path_returns_empty(self) -> None:
        assert render_breadcrumb([], depth=-1) == ""

    def test_blank_titles_filtered(self) -> None:
        assert render_breadcrumb(["", "Install", "  "], depth=-1) == "Install"

    def test_rejects_invalid_negative_depth(self) -> None:
        with pytest.raises(ValueError, match="depth"):
            render_breadcrumb(["A"], depth=-2)


class TestPrependBreadcrumb:
    def test_prepends_with_blank_line(self) -> None:
        out = prepend_breadcrumb("contenu", ["Guide", "Install"], depth=-1)
        assert out == "Guide > Install\n\ncontenu"

    def test_no_breadcrumb_returns_content_unchanged(self) -> None:
        assert prepend_breadcrumb("contenu", [], depth=-1) == "contenu"
        assert prepend_breadcrumb("contenu", ["A"], depth=0) == "contenu"
