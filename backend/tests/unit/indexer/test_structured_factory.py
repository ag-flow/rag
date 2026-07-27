from __future__ import annotations

from uuid import uuid4

import pytest

from rag.indexer.chunking.cleaner import CleaningChunkerWrapper
from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.region_routes import RegionRoute
from rag.indexer.chunking.routing_chunker import RoutingChunker
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.table import TableChunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=4.0)


class TestDispatch:
    def test_prose_algo_returns_markdown_deep(self) -> None:
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, MarkdownDeepChunker)

    def test_markdown_alias_of_prose(self) -> None:
        chunker = make_structured_chunker(
            algo="markdown",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, MarkdownDeepChunker)

    def test_table_algo_returns_table_chunker(self) -> None:
        chunker = make_structured_chunker(
            algo="table",
            params={"child_target_tokens": 384, "max_rows_per_chunk": 20},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        assert isinstance(chunker, TableChunker)

    def test_unknown_algo_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown chunking algo"):
            make_structured_chunker(
                algo="quantum",
                params={},
                estimator=_EST,
                provider_max_input_tokens=8192,
            )

    def test_unknown_param_key_rejected(self) -> None:
        with pytest.raises(ValueError, match="unknown"):
            make_structured_chunker(
                algo="prose",
                params={"child_target_tokens": 384, "bogus": 1},
                estimator=_EST,
                provider_max_input_tokens=8192,
            )


class TestHardCeilingWiring:
    def test_hard_ceiling_derived_from_provider_limit(self) -> None:
        # provider 10 tokens, safety 0.8 → hard ceiling 8 ; mot insécable de
        # ~25 chars (≈7 tokens à ratio 4)… on force un mot bien au-delà.
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 8, "overlap_tokens": 0, "floor_tokens": 0},
            estimator=_EST,
            provider_max_input_tokens=10,
            safety_factor=0.8,
        )
        giant = "x" * 200  # ≈50 tokens > hard ceiling 8
        with pytest.raises(ChunkTooLargeError):
            chunker.chunk(f"# S\n\n{giant}")

    def test_child_target_clamped_to_hard_ceiling(self) -> None:
        # child_target demandé 384 mais provider minuscule → clamp, pas de crash
        chunker = make_structured_chunker(
            algo="prose",
            params={"child_target_tokens": 384},
            estimator=_EST,
            provider_max_input_tokens=20,
        )
        doc = chunker.chunk("# S\n\nshort body")
        assert doc.parents


class TestRoutingBranch:
    def test_parser_slug_returns_routing_chunker(self) -> None:
        chunker = make_structured_chunker(
            algo="prose",
            params={},
            estimator=_EST,
            provider_max_input_tokens=8192,
            parser_slug="markdown",
        )
        assert isinstance(chunker, RoutingChunker)

    def test_parser_slug_composes_with_cleaning(self) -> None:
        chunker = make_structured_chunker(
            algo="markdown",
            params={"clean_content": True},
            estimator=_EST,
            provider_max_input_tokens=8192,
            parser_slug="markdown",
        )
        assert isinstance(chunker, CleaningChunkerWrapper)

    def test_unknown_parser_slug_raises(self) -> None:
        with pytest.raises(ValueError, match="parser"):
            make_structured_chunker(
                algo="prose",
                params={},
                estimator=_EST,
                provider_max_input_tokens=8192,
                parser_slug="pdf",
            )

    def test_parser_slug_requires_prose_algo(self) -> None:
        with pytest.raises(ValueError, match="prose"):
            make_structured_chunker(
                algo="table",
                params={},
                estimator=_EST,
                provider_max_input_tokens=8192,
                parser_slug="markdown",
            )

    def test_route_target_without_bound_chunker_raises(self) -> None:
        target_id = uuid4()
        route = RegionRoute(
            region_type="code_fence", qualifier="mermaid", target_strategy_id=target_id
        )
        with pytest.raises(ValueError, match=str(target_id)):
            make_structured_chunker(
                algo="prose",
                params={},
                estimator=_EST,
                provider_max_input_tokens=8192,
                parser_slug="markdown",
                region_routes=[route],
            )

    def test_route_targets_are_wired(self) -> None:
        target_id = uuid4()
        route = RegionRoute(region_type="code_fence", qualifier="*", target_strategy_id=target_id)
        target = make_structured_chunker(
            algo="prose", params={}, estimator=_EST, provider_max_input_tokens=8192
        )
        chunker = make_structured_chunker(
            algo="prose",
            params={},
            estimator=_EST,
            provider_max_input_tokens=8192,
            parser_slug="markdown",
            region_routes=[route],
            route_targets={target_id: target},
        )
        doc = chunker.chunk("# T\n\n```sh\nls -la\n```\n")
        assert any("ls -la" in c.embed_text for c in doc.children)


class TestDefaults:
    def test_prose_defaults_applied(self) -> None:
        # sans params → defaults raisonnables, ne lève pas
        chunker = make_structured_chunker(
            algo="prose",
            params={},
            estimator=_EST,
            provider_max_input_tokens=8192,
        )
        doc = chunker.chunk("# Guide\n\n## Sub\n\nbody")
        assert {p.section_key for p in doc.parents} == {"Guide", "Guide/Sub"}


class TestValidateStrategySpec:
    """Validation de spec sans construction (CRUD admin, F3)."""

    def test_valid_spec_passes(self) -> None:
        from rag.indexer.chunking.structured_factory import validate_strategy_spec

        validate_strategy_spec(
            algo="prose", params={"child_target_tokens": 256}, parser_slug="markdown"
        )

    def test_unknown_algo_raises(self) -> None:
        from rag.indexer.chunking.structured_factory import validate_strategy_spec

        with pytest.raises(ValueError, match="unknown chunking algo"):
            validate_strategy_spec(algo="quantum", params={})

    def test_parser_on_non_prose_algo_raises(self) -> None:
        from rag.indexer.chunking.structured_factory import validate_strategy_spec

        with pytest.raises(ValueError, match="parser_slug requires a prose algo"):
            validate_strategy_spec(algo="table", params={}, parser_slug="markdown")

    def test_unknown_param_raises(self) -> None:
        from rag.indexer.chunking.structured_factory import validate_strategy_spec

        with pytest.raises(ValueError, match="unknown params"):
            validate_strategy_spec(algo="table", params={"heading_levels": [1]})
