from __future__ import annotations

from uuid import uuid4

import pytest

from rag.indexer.chunking.region_routes import (
    OVERFLOW_POLICIES,
    RegionRoute,
    resolve_region_route,
)


class TestRegionRouteModel:
    def test_defaults_are_wildcard_inline_keep_whole(self) -> None:
        route = RegionRoute(region_type="code_fence")
        assert route.qualifier == "*"
        assert route.target_strategy_id is None
        assert route.atomic is False
        assert route.overflow_policy == "keep_whole"

    def test_unknown_region_type_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="mermaid"):
            RegionRoute(region_type="mermaid")

    def test_unknown_overflow_policy_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="truncate"):
            RegionRoute(region_type="table", overflow_policy="truncate")

    def test_empty_qualifier_is_rejected(self) -> None:
        with pytest.raises(ValueError, match="qualifier"):
            RegionRoute(region_type="code_fence", qualifier="")

    def test_the_three_policies_exist(self) -> None:
        expected = frozenset({"keep_whole", "split_fallback", "parent_only"})
        assert expected == OVERFLOW_POLICIES


class TestResolutionBySpecificity:
    def test_exact_match_beats_wildcard(self) -> None:
        wildcard = RegionRoute(region_type="code_fence", qualifier="*", atomic=True)
        exact = RegionRoute(
            region_type="code_fence", qualifier="mermaid", overflow_policy="parent_only"
        )
        routes = [wildcard, exact]
        resolved = resolve_region_route(routes, region_type="code_fence", qualifier="mermaid")
        assert resolved is exact

    def test_wildcard_when_no_exact_match(self) -> None:
        wildcard = RegionRoute(region_type="code_fence", qualifier="*", atomic=True)
        exact = RegionRoute(region_type="code_fence", qualifier="mermaid")
        resolved = resolve_region_route(
            [exact, wildcard], region_type="code_fence", qualifier="python"
        )
        assert resolved is wildcard

    def test_none_when_type_has_no_route(self) -> None:
        routes = [RegionRoute(region_type="table", qualifier="*")]
        assert resolve_region_route(routes, region_type="code_fence", qualifier="python") is None

    def test_unqualified_region_matches_only_wildcard(self) -> None:
        exact = RegionRoute(region_type="code_fence", qualifier="mermaid")
        assert resolve_region_route([exact], region_type="code_fence", qualifier=None) is None
        wildcard = RegionRoute(region_type="code_fence", qualifier="*")
        resolved = resolve_region_route([exact, wildcard], region_type="code_fence", qualifier=None)
        assert resolved is wildcard

    def test_route_can_carry_a_target_strategy(self) -> None:
        target_id = uuid4()
        route = RegionRoute(
            region_type="code_fence", qualifier="mermaid", target_strategy_id=target_id
        )
        assert route.target_strategy_id == target_id
