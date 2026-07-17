from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.chunking_strategies import (
    RegionRouteSpec,
    RoutesUpdate,
    StrategyCreate,
    StrategyPatch,
)
from rag.schemas.slug import slugify


class TestSlugify:
    def test_convention_docflow(self) -> None:
        assert slugify("Markdown Deep (perso)") == "markdown-deep-perso"

    def test_accents_translitteres(self) -> None:
        assert slugify("Stratégie n°1 — été") == "strategie-n1-ete"

    def test_label_sans_slug(self) -> None:
        assert slugify("!!!") == ""


class TestRegionRouteSpec:
    def test_defaults(self) -> None:
        route = RegionRouteSpec(region_type="code_fence")
        assert (route.qualifier, route.atomic, route.overflow_policy) == (
            "*",
            False,
            "keep_whole",
        )
        assert route.target_strategy_id is None

    def test_unknown_region_type_rejected(self) -> None:
        with pytest.raises(ValidationError, match="type de région inconnu"):
            RegionRouteSpec(region_type="mermaid")

    def test_unknown_policy_rejected(self) -> None:
        with pytest.raises(ValidationError, match="politique de débordement"):
            RegionRouteSpec(region_type="table", overflow_policy="truncate")

    def test_empty_qualifier_rejected(self) -> None:
        with pytest.raises(ValidationError):
            RegionRouteSpec(region_type="table", qualifier="")


class TestRoutesUpdate:
    def test_duplicate_key_rejected(self) -> None:
        with pytest.raises(ValidationError, match="routes en double"):
            RoutesUpdate(
                routes=[
                    RegionRouteSpec(region_type="table"),
                    RegionRouteSpec(region_type="table"),
                ]
            )

    def test_same_type_distinct_qualifiers_ok(self) -> None:
        update = RoutesUpdate(
            routes=[
                RegionRouteSpec(region_type="code_fence", qualifier="mermaid"),
                RegionRouteSpec(region_type="code_fence"),
            ]
        )
        assert len(update.routes) == 2


class TestStrategyCreate:
    def test_unknown_algo_rejected(self) -> None:
        with pytest.raises(ValidationError, match="algo inconnu"):
            StrategyCreate(label="Quantum", algo="quantum")

    def test_params_default_empty(self) -> None:
        req = StrategyCreate(label="Prose", algo="prose")
        assert req.params == {}
        assert req.parser_slug is None


class TestStrategyPatch:
    def test_parser_slug_absent_vs_explicit_none(self) -> None:
        """Le service distingue « ne pas toucher » de « retirer le parser »
        via model_fields_set."""
        untouched = StrategyPatch(label="Nouveau nom")
        cleared = StrategyPatch(parser_slug=None)
        assert "parser_slug" not in untouched.model_fields_set
        assert "parser_slug" in cleared.model_fields_set
