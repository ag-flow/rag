from __future__ import annotations

from uuid import uuid4

import pytest

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.markdown_regions import MarkdownRegionParser
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.region_routes import RegionRoute
from rag.indexer.chunking.routing_chunker import RoutingChunker
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, ParentSection
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_EST = HeuristicTokenEstimator(char_ratio=1.0)
_PARSER = MarkdownRegionParser()


def _bounds(
    *, target: int = 2000, floor: int = 0, overlap: int = 0, hard: int = 8000
) -> TokenBounds:
    return TokenBounds(
        child_target_tokens=target,
        floor_tokens=floor,
        overlap_tokens=overlap,
        hard_ceiling_tokens=hard,
    )


def _routing(
    *,
    routes: list[RegionRoute] | None = None,
    targets: dict | None = None,
    bounds: TokenBounds | None = None,
    depth: int = -1,
    heading_levels: tuple[int, ...] = (1, 2),
) -> RoutingChunker:
    return RoutingChunker(
        parser=_PARSER,
        routes=routes or [],
        targets=targets or {},
        estimator=_EST,
        bounds=bounds or _bounds(),
        breadcrumb_depth=depth,
        heading_levels=heading_levels,
    )


def _deep(*, bounds: TokenBounds | None = None, depth: int = -1) -> MarkdownDeepChunker:
    return MarkdownDeepChunker(
        estimator=_EST,
        bounds=bounds or _bounds(),
        breadcrumb_depth=depth,
        heading_levels=(1, 2),
    )


class _StubTarget:
    """Cible factice : retourne des enfants fixes, mémorise l'entrée reçue."""

    def __init__(self, *, children_texts: list[str] | None = None) -> None:
        self.received: list[str] = []
        self._texts = children_texts if children_texts is not None else ["DESC"]

    def chunk(self, content: str) -> ChunkedDocument:
        self.received.append(content)
        parent = ParentSection(section_key="sub", content=content)
        children = [ChildChunk(embed_text=t, parent_key="sub") for t in self._texts]
        return ChunkedDocument(parents=[parent], children=children)


class _ExplodingTarget:
    def chunk(self, content: str) -> ChunkedDocument:
        raise ChunkTooLargeError(estimated_tokens=9999, hard_ceiling_tokens=10)


class TestEquivalenceWithoutRoutes:
    @pytest.mark.parametrize(
        "doc",
        [
            "",
            "   \n  ",
            "sans titre, juste du texte.\n\nsecond paragraphe.",
            "# Guide\n\nIntro.\n\n## Section\n\nDétail.",
            "préambule\n\n# Guide\n\n```python\nprint('x')\n```\n\nsuite",
            "---\ntitle: X\n---\n\n# T\n\n| a |\n| - |\n| 1 |\n\nfin",
            "# A\n\n## B\n\ntexte\n\n## B\n\ndoublon de titre",
        ],
    )
    def test_no_route_output_is_bit_identical_to_markdown_deep(self, doc: str) -> None:
        assert _routing().chunk(doc) == _deep().chunk(doc)

    def test_equivalence_holds_with_floor_and_overlap(self) -> None:
        doc = "# T\n\npetit.\n\nsecond bloc un peu plus long.\n\ntroisième."
        bounds = _bounds(target=30, floor=10, overlap=5)
        assert _routing(bounds=bounds).chunk(doc) == _deep(bounds=bounds).chunk(doc)

    def test_explicit_inline_route_matches_default_behaviour(self) -> None:
        doc = "# T\n\navant\n\n| a |\n| - |\n\naprès"
        inline = RegionRoute(region_type="table", qualifier="*")
        assert _routing(routes=[inline]).chunk(doc) == _deep().chunk(doc)


class TestAtomicInline:
    def test_atomic_table_is_never_merged_with_prose(self) -> None:
        doc = "# T\n\npara.\n\n| a |\n| - |\n\npara2."
        bounds = _bounds(target=200, floor=100)
        merged = _routing(bounds=bounds).chunk(doc)
        assert len(merged.children) == 1  # sans route, tout fusionne sous le floor

        route = RegionRoute(region_type="table", qualifier="*", atomic=True)
        doc_routed = _routing(routes=[route], bounds=bounds).chunk(doc)
        texts = [c.embed_text for c in doc_routed.children]
        assert any(t.endswith("| a |\n| - |") for t in texts)
        assert len(doc_routed.children) == 3


class TestParentOnly:
    def test_region_stays_in_parent_but_is_not_embedded(self) -> None:
        doc = "# T\n\nintro\n\n```mermaid\ngraph TD\n```\n\nsuite"
        route = RegionRoute(
            region_type="code_fence", qualifier="mermaid", overflow_policy="parent_only"
        )
        result = _routing(routes=[route]).chunk(doc)
        assert "graph TD" in result.parents[0].content
        assert all("graph TD" not in c.embed_text for c in result.children)
        assert any("intro" in c.embed_text for c in result.children)
        assert any("suite" in c.embed_text for c in result.children)


class TestTargetRouting:
    def test_region_content_is_chunked_by_target(self) -> None:
        target_id = uuid4()
        stub = _StubTarget()
        route = RegionRoute(
            region_type="code_fence", qualifier="mermaid", target_strategy_id=target_id
        )
        doc = "# Guide\n\n## Install\n\n```mermaid\ngraph TD\n```\n"
        _routing(routes=[route], targets={target_id: stub}).chunk(doc)
        assert stub.received == ["```mermaid\ngraph TD\n```"]

    def test_target_children_are_reparented_and_breadcrumbed(self) -> None:
        target_id = uuid4()
        route = RegionRoute(
            region_type="code_fence", qualifier="mermaid", target_strategy_id=target_id
        )
        doc = "# Guide\n\n## Install\n\n```mermaid\ngraph TD\n```\n"
        result = _routing(routes=[route], targets={target_id: _StubTarget()}).chunk(doc)
        routed = [c for c in result.children if "DESC" in c.embed_text]
        assert len(routed) == 1
        child = routed[0]
        assert child.embed_text == "Guide > Install\n\nDESC"
        assert child.parent_key == "Guide/Install"
        assert child.metadata["region_type"] == "code_fence"
        assert child.metadata["region_qualifier"] == "mermaid"

    def test_children_keep_document_order_around_target(self) -> None:
        target_id = uuid4()
        route = RegionRoute(region_type="code_fence", qualifier="*", target_strategy_id=target_id)
        doc = "# T\n\navant\n\n```sh\nls\n```\n\naprès"
        result = _routing(routes=[route], targets={target_id: _StubTarget()}).chunk(doc)
        positions = [
            next(i for i, c in enumerate(result.children) if marker in c.embed_text)
            for marker in ("avant", "DESC", "après")
        ]
        assert positions == sorted(positions)

    def test_missing_target_chunker_raises(self) -> None:
        route = RegionRoute(region_type="code_fence", qualifier="*", target_strategy_id=uuid4())
        with pytest.raises(ValueError, match="target"):
            _routing(routes=[route]).chunk("```sh\nls\n```\n")


class TestSpecificityInDocument:
    def test_exact_and_wildcard_routes_coexist(self) -> None:
        routes = [
            RegionRoute(
                region_type="code_fence", qualifier="mermaid", overflow_policy="parent_only"
            ),
            RegionRoute(region_type="code_fence", qualifier="*", atomic=True),
        ]
        doc = "# T\n\n```mermaid\ngraph TD\n```\n\n```python\nprint('x')\n```\n"
        result = _routing(routes=routes).chunk(doc)
        texts = [c.embed_text for c in result.children]
        assert all("graph TD" not in t for t in texts)
        assert any("print('x')" in t for t in texts)


class TestOverflowPolicies:
    def test_keep_whole_raises_beyond_hard_ceiling(self) -> None:
        giant = "x" * 500
        doc = f"# T\n\n```mermaid\n{giant}\n```\n"
        route = RegionRoute(region_type="code_fence", qualifier="*", atomic=True)
        chunker = _routing(routes=[route], bounds=_bounds(target=50, hard=100))
        with pytest.raises(ChunkTooLargeError):
            chunker.chunk(doc)

    def test_split_fallback_splits_instead_of_raising(self) -> None:
        giant = "mot " * 200
        doc = f"# T\n\n```mermaid\n{giant.strip()}\n```\n"
        route = RegionRoute(
            region_type="code_fence",
            qualifier="*",
            atomic=True,
            overflow_policy="split_fallback",
        )
        result = _routing(routes=[route], bounds=_bounds(target=50, hard=100)).chunk(doc)
        assert len(result.children) > 1

    def test_target_error_propagates_with_keep_whole(self) -> None:
        target_id = uuid4()
        route = RegionRoute(region_type="code_fence", qualifier="*", target_strategy_id=target_id)
        chunker = _routing(routes=[route], targets={target_id: _ExplodingTarget()})
        with pytest.raises(ChunkTooLargeError):
            chunker.chunk("```sh\nls\n```\n")

    def test_target_error_falls_back_to_split_with_split_fallback(self) -> None:
        target_id = uuid4()
        route = RegionRoute(
            region_type="code_fence",
            qualifier="*",
            target_strategy_id=target_id,
            overflow_policy="split_fallback",
        )
        doc = "```sh\n" + "mot " * 200 + "\n```\n"
        chunker = _routing(
            routes=[route],
            targets={target_id: _ExplodingTarget()},
            bounds=_bounds(target=50, hard=100),
        )
        result = chunker.chunk(doc)
        assert len(result.children) > 1


class TestDroppedRegions:
    """Les régions `parent_only` sont rapportées pour le contextual retrieval."""

    def test_parent_only_region_reported_with_anchor(self) -> None:
        chunker = _routing(
            routes=[
                RegionRoute(
                    region_type="code_fence", qualifier="mermaid", overflow_policy="parent_only"
                )
            ]
        )
        doc = chunker.chunk("# Archi\n\nIntro.\n\n```mermaid\ngraph TD; A-->B;\n```\n")
        assert len(doc.dropped_regions) == 1
        dropped = doc.dropped_regions[0]
        assert (dropped.region_type, dropped.qualifier) == ("code_fence", "mermaid")
        assert "graph TD" in dropped.content
        assert dropped.parent_key == "Archi"
        assert dropped.crumb == ("Archi",)

    def test_no_routes_no_dropped_regions(self) -> None:
        doc = _routing().chunk("# T\n\n```mermaid\ngraph TD; A-->B;\n```\n")
        assert doc.dropped_regions == []
