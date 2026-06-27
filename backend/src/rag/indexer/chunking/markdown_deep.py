from __future__ import annotations

from collections import Counter
from typing import Any

from rag.indexer.chunking._sections import Section, split_blocks, split_into_sections
from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.normalizer import TokenBounds, TokenNormalizer
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, ParentSection
from rag.indexer.chunking.tokens import TokenEstimator

_ROOT_KEY = "(root)"


class MarkdownDeepChunker:
    """Stratégie prose structure-aware (small-to-big).

    Par section H{n} : émet une `ParentSection` (texte brut renvoyé au LLM) et
    N `ChildChunk` (paragraphes normalisés en tokens + breadcrumb, embeddés).
    Compose `TokenNormalizer` (bornes), `prepend_breadcrumb` (contexte) et le
    sectionnement Markdown. Les fences de code sont préservées comme blocs
    atomiques (plus de fence non bornée).
    """

    def __init__(
        self,
        *,
        estimator: TokenEstimator,
        bounds: TokenBounds,
        breadcrumb_depth: int,
        heading_levels: tuple[int, ...],
    ) -> None:
        self._normalizer = TokenNormalizer(estimator, bounds)
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
        seen: Counter[str] = Counter()

        for section in sections:
            key = self._section_key(section, seen)
            meta = self._meta(section)
            parents.append(ParentSection(section_key=key, content=section.content, metadata=meta))
            crumb_path = self._crumb_path(section)
            for piece in self._normalizer.normalize(split_blocks(section.content)):
                children.append(
                    ChildChunk(
                        embed_text=prepend_breadcrumb(piece, crumb_path, depth=self._depth),
                        parent_key=key,
                        metadata=meta,
                    )
                )

        return ChunkedDocument(parents=parents, children=children)

    @staticmethod
    def _meta(section: Section) -> dict[str, Any]:
        return {
            "section_title": section.title,
            "section_path": section.path,
            "heading_level": section.level,
        }

    @staticmethod
    def _crumb_path(section: Section) -> list[str]:
        own = [section.title] if section.title else []
        return [*section.path, *own]

    @staticmethod
    def _section_key(section: Section, seen: Counter[str]) -> str:
        titles = [t for t in [*section.path, section.title] if t and t.strip()]
        base = "/".join(titles) if titles else _ROOT_KEY
        seen[base] += 1
        occurrence = seen[base]
        return base if occurrence == 1 else f"{base}#{occurrence}"
