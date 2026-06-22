from __future__ import annotations

from typing import Any

from rag.indexer.chunking._sections import Section, scan_fences, split_into_sections
from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import Chunk


class MarkdownChunker:
    """Découpe un document Markdown par sections H{n} avec respect des fences.

    Algorithme :
      1. Découpe en sections sur les titres dont le niveau est dans
         heading_levels (cf. `_sections.split_into_sections`).
      2. Pour chaque section, sub-split si > max_chars en préservant les fences.
      3. Cas particulier : aucun heading aux niveaux configurés → délègue
         à ParagraphChunker, metadata neutre.
      4. Préambule (texte avant 1er heading) → section "fictive" avec
         section_title=None, heading_level=0.

    Stratégie legacy (plate, char-based) — conservée derrière le flag
    `chunking.engine=legacy`. La stratégie structure-aware vit dans
    `markdown_deep.MarkdownDeepChunker`.
    """

    def __init__(
        self,
        *,
        max_chars: int,
        min_chars: int,
        overlap_chars: int,
        heading_levels: tuple[int, ...],
    ) -> None:
        self._max_chars = max_chars
        self._min_chars = min_chars
        self._overlap_chars = overlap_chars
        self._heading_levels = heading_levels
        self._paragraph_fallback = ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )

    def chunk(self, content: str) -> list[Chunk]:
        if not content.strip():
            return []
        sections = split_into_sections(content, heading_levels=self._heading_levels)
        if not sections:
            return self._enrich_with_neutral_metadata(
                self._paragraph_fallback.chunk(content),
            )
        result: list[Chunk] = []
        for section in sections:
            result.extend(self._chunk_section(section))
        return result

    @staticmethod
    def _enrich_with_neutral_metadata(chunks: list[Chunk]) -> list[Chunk]:
        """Pour le cas no-heading : ré-emballe chaque Chunk avec la valeur
        neutre de metadata. Le dict est reconstruit à chaque chunk pour éviter
        le partage par référence (Chunk est frozen mais metadata=Mapping reste
        techniquement mutable au runtime)."""
        return [
            Chunk(
                content=c.content,
                metadata={
                    "section_title": None,
                    "section_path": [],
                    "heading_level": 0,
                },
            )
            for c in chunks
        ]

    def _chunk_section(self, section: Section) -> list[Chunk]:
        meta: dict[str, Any] = {
            "section_title": section.title,
            "section_path": section.path,
            "heading_level": section.level,
        }
        if len(section.content) <= self._max_chars:
            return [Chunk(content=section.content, metadata=meta)]
        return self._subsplit_with_fences(section, meta)

    def _subsplit_with_fences(
        self,
        section: Section,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        section_lines = section.content.splitlines(keepends=False)
        fence_ranges_rel = scan_fences(section_lines)
        if not fence_ranges_rel:
            return self._chunks_from_text_block(section.content, meta)

        chunks: list[Chunk] = []
        cursor = 0
        for fence_start, fence_end in fence_ranges_rel:
            if cursor < fence_start:
                text_lines = section_lines[cursor:fence_start]
                text_block = "\n".join(text_lines).strip()
                if text_block:
                    chunks.extend(self._chunks_from_text_block(text_block, meta))
            fence_lines = section_lines[fence_start:fence_end]
            fence_text = "\n".join(fence_lines)
            chunks.append(Chunk(content=fence_text, metadata=meta))
            cursor = fence_end

        if cursor < len(section_lines):
            tail_lines = section_lines[cursor:]
            tail_text = "\n".join(tail_lines).strip()
            if tail_text:
                chunks.extend(self._chunks_from_text_block(tail_text, meta))

        return chunks

    def _chunks_from_text_block(
        self,
        text: str,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        sub_chunks = self._paragraph_fallback.chunk(text)
        return [Chunk(content=c.content, metadata=meta) for c in sub_chunks]
