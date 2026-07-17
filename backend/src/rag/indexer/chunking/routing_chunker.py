from __future__ import annotations

from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID

from rag.indexer.chunking._sections import Section, split_blocks, split_into_sections
from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.markdown_deep import section_crumb_path, section_key, section_meta
from rag.indexer.chunking.normalizer import Block, TokenBounds, TokenNormalizer
from rag.indexer.chunking.region_routes import RegionRoute, resolve_region_route
from rag.indexer.chunking.regions import Region, RegionParser
from rag.indexer.chunking.structured import (
    ChildChunk,
    ChunkedDocument,
    DroppedRegion,
    ParentSection,
    StructuredChunkerProtocol,
)
from rag.indexer.chunking.tokens import TokenEstimator


class RoutingChunker:
    """Composite région-aware : parse en régions, route chaque région (spec §3).

    Le squelette small-to-big est celui de `MarkdownDeepChunker` (mêmes
    sections, clés, métadonnées, breadcrumbs). Les régions non routées sont
    concaténées puis passées à `split_blocks` — la propriété de reconstruction
    du parser garantit un comportement **bit-à-bit identique** à l'existant
    quand aucune route ne matche. Les parents contiennent toujours le texte
    intégral de la section (y compris régions `parent_only`).
    """

    def __init__(
        self,
        *,
        parser: RegionParser,
        routes: Sequence[RegionRoute],
        targets: Mapping[UUID, StructuredChunkerProtocol],
        estimator: TokenEstimator,
        bounds: TokenBounds,
        breadcrumb_depth: int,
        heading_levels: tuple[int, ...],
    ) -> None:
        self._parser = parser
        self._routes = tuple(routes)
        self._targets = dict(targets)
        self._est = estimator
        self._normalizer = TokenNormalizer(estimator, bounds)
        self._hard = bounds.hard_ceiling_tokens
        self._depth = breadcrumb_depth
        self._heading_levels = heading_levels

    def chunk(self, content: str) -> ChunkedDocument:
        if not content.strip():
            return ChunkedDocument(parents=[], children=[])
        sections = split_into_sections(content, heading_levels=self._heading_levels)
        if not sections:
            sections = [Section(title=None, path=[], level=0, content=content)]

        parents: list[ParentSection] = []
        children: list[ChildChunk] = []
        dropped: list[DroppedRegion] = []
        seen: Counter[str] = Counter()
        for section in sections:
            key = section_key(section, seen)
            meta = section_meta(section)
            parents.append(ParentSection(section_key=key, content=section.content, metadata=meta))
            children.extend(self._section_children(section, key, meta, dropped))
        return ChunkedDocument(parents=parents, children=children, dropped_regions=dropped)

    def _section_children(
        self, section: Section, key: str, meta: dict[str, Any], dropped: list[DroppedRegion]
    ) -> list[ChildChunk]:
        out: list[ChildChunk] = []
        blocks: list[Block] = []
        inline: list[str] = []
        crumb = section_crumb_path(section)
        for region in self._parser.parse(section.content):
            route = resolve_region_route(
                self._routes, region_type=region.type, qualifier=region.qualifier
            )
            if route is None:
                inline.append(region.content)
                continue
            self._flush_inline(inline, blocks)
            self._apply_route(route, region, section, key, meta, crumb, blocks, out, dropped)
        self._flush_inline(inline, blocks)
        self._emit_blocks(blocks, crumb, key, meta, out)
        return out

    def _apply_route(
        self,
        route: RegionRoute,
        region: Region,
        section: Section,
        key: str,
        meta: dict[str, Any],
        crumb: list[str],
        blocks: list[Block],
        out: list[ChildChunk],
        dropped: list[DroppedRegion],
    ) -> None:
        if route.overflow_policy == "parent_only":
            # Restituée via le parent, jamais embeddée — mais rapportée pour
            # le contextual retrieval (description LLM embeddable à la place).
            dropped.append(
                DroppedRegion(
                    region_type=region.type,
                    qualifier=region.qualifier,
                    content=region.content,
                    parent_key=key,
                    crumb=tuple([*section.path, *region.heading_path]),
                    breadcrumb_depth=self._depth,
                )
            )
            return
        if route.target_strategy_id is not None:
            self._emit_blocks(blocks, crumb, key, meta, out)  # préserve l'ordre document
            self._emit_target(route, region, section, key, meta, out)
        elif route.atomic:
            blocks.append(self._atomic_block(region, route))
        else:
            blocks.extend(split_blocks(region.content))  # inline explicite = défaut

    def _atomic_block(self, region: Region, route: RegionRoute) -> Block:
        text = region.content.strip("\n")
        overflows = self._est.estimate(text) > self._hard
        if overflows and route.overflow_policy == "split_fallback":
            return Block.prose(text)
        return Block(text=text, atomic=True)

    def _emit_target(
        self,
        route: RegionRoute,
        region: Region,
        section: Section,
        key: str,
        meta: dict[str, Any],
        out: list[ChildChunk],
    ) -> None:
        target = self._targets.get(route.target_strategy_id)
        if target is None:
            raise ValueError(f"no chunker bound for target strategy {route.target_strategy_id}")
        crumb = [*section.path, *region.heading_path]
        region_meta = {**meta, "region_type": region.type, "region_qualifier": region.qualifier}
        try:
            sub = target.chunk(region.content)
        except ChunkTooLargeError:
            if route.overflow_policy != "split_fallback":
                raise
            fallback = [Block.prose(region.content.strip("\n"))]
            self._emit_blocks(fallback, crumb, key, region_meta, out)
            return
        for child in sub.children:
            out.append(
                ChildChunk(
                    embed_text=prepend_breadcrumb(child.embed_text, crumb, depth=self._depth),
                    parent_key=key,
                    metadata=region_meta,
                )
            )

    def _emit_blocks(
        self,
        blocks: list[Block],
        crumb: list[str],
        key: str,
        meta: dict[str, Any],
        out: list[ChildChunk],
    ) -> None:
        if not blocks:
            return
        for piece in self._normalizer.normalize(blocks):
            out.append(
                ChildChunk(
                    embed_text=prepend_breadcrumb(piece, crumb, depth=self._depth),
                    parent_key=key,
                    metadata=meta,
                )
            )
        blocks.clear()

    @staticmethod
    def _flush_inline(inline: list[str], blocks: list[Block]) -> None:
        if inline:
            blocks.extend(split_blocks("".join(inline)))
            inline.clear()
