from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from markdown_it import MarkdownIt
from markdown_it.token import Token

from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import Chunk


@dataclass
class _Section:
    """Section interne du chunker. Jamais exposée hors du module."""

    title: str | None
    path: list[str]
    level: int
    content: str


class MarkdownChunker:
    """Découpe un document Markdown par sections H{n} avec respect des fences.

    Algorithme :
      1. Parse via markdown-it-py.
      2. Découpe en sections sur les tokens heading_open dont le niveau est
         dans heading_levels.
      3. Pour chaque section, sub-split si > max_chars en préservant les fences.
      4. Cas particulier : aucun heading aux niveaux configurés → délègue
         à ParagraphChunker, metadata neutre.
      5. Préambule (texte avant 1er heading) → section "fictive" avec
         section_title=None, heading_level=0.
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
        self._md = MarkdownIt("commonmark")
        self._paragraph_fallback = ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )

    def chunk(self, content: str) -> list[Chunk]:
        if not content.strip():
            return []
        sections = self._split_into_sections(content)
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

    def _split_into_sections(self, content: str) -> list[_Section]:
        tokens = self._md.parse(content)
        lines = content.splitlines(keepends=False)
        sections: list[_Section] = []
        breadcrumb: list[tuple[int, str]] = []
        current_start_line: int | None = None
        current_meta: tuple[str | None, list[str], int] | None = None
        first_section_start_line: int | None = None

        def flush_section(end_line: int) -> None:
            nonlocal current_start_line, current_meta
            if current_start_line is None or current_meta is None:
                return
            section_text = "\n".join(lines[current_start_line:end_line])
            title, path, level = current_meta
            sections.append(
                _Section(
                    title=title,
                    path=path,
                    level=level,
                    content=section_text,
                ),
            )

        for i, tok in enumerate(tokens):
            if tok.type == "heading_open":
                heading_level = int(tok.tag[1])
                title = self._extract_heading_title(tokens, i)
                while breadcrumb and breadcrumb[-1][0] >= heading_level:
                    breadcrumb.pop()
                breadcrumb.append((heading_level, title))

                if heading_level in self._heading_levels:
                    start_line = tok.map[0] if tok.map else 0
                    if first_section_start_line is None:
                        first_section_start_line = start_line
                    flush_section(start_line)
                    current_start_line = start_line
                    current_meta = (title, [t for _, t in breadcrumb[:-1]], heading_level)

        if current_start_line is not None:
            flush_section(len(lines))

        if sections and first_section_start_line is not None and first_section_start_line > 0:
            pre_lines = "\n".join(lines[:first_section_start_line])
            if pre_lines.strip():
                sections.insert(
                    0,
                    _Section(
                        title=None,
                        path=[],
                        level=0,
                        content=pre_lines,
                    ),
                )

        return sections

    @staticmethod
    def _extract_heading_title(tokens: list[Token], heading_open_index: int) -> str:
        if heading_open_index + 1 < len(tokens):
            inline_tok = tokens[heading_open_index + 1]
            if inline_tok.type == "inline" and inline_tok.content:
                return inline_tok.content.strip()
        return ""

    def _chunk_section(self, section: _Section) -> list[Chunk]:
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
        section: _Section,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        section_lines = section.content.splitlines(keepends=False)
        fence_ranges_rel = self._scan_fences_in_lines(section_lines)
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

    @staticmethod
    def _scan_fences_in_lines(lines: list[str]) -> list[tuple[int, int]]:
        ranges: list[tuple[int, int]] = []
        in_fence = False
        fence_marker = ""
        start = 0
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
                in_fence = True
                fence_marker = stripped[:3]
                start = i
            elif in_fence and stripped.startswith(fence_marker):
                ranges.append((start, i + 1))
                in_fence = False
        if in_fence:
            ranges.append((start, len(lines)))
        return ranges

    def _chunks_from_text_block(
        self,
        text: str,
        meta: dict[str, Any],
    ) -> list[Chunk]:
        sub_chunks = self._paragraph_fallback.chunk(text)
        return [Chunk(content=c.content, metadata=meta) for c in sub_chunks]
