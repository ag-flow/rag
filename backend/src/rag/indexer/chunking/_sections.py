from __future__ import annotations

from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.token import Token

from rag.indexer.chunking.normalizer import Block


@dataclass(frozen=True)
class Section:
    """Section Markdown : titre, chemin des ancêtres, niveau, contenu brut.

    `path` = titres des ancêtres (hors titre courant). `content` inclut la
    ligne de titre. Pour le préambule (texte avant le 1er titre) : `title=None`,
    `path=[]`, `level=0`.
    """

    title: str | None
    path: list[str]
    level: int
    content: str


def split_into_sections(content: str, *, heading_levels: tuple[int, ...]) -> list[Section]:
    """Découpe `content` en sections sur les titres dont le niveau ∈ `heading_levels`.

    Retourne `[]` si aucun titre aux niveaux configurés. Le préambule éventuel
    devient une section `level=0` insérée en tête.
    """
    md = MarkdownIt("commonmark")
    tokens = md.parse(content)
    lines = content.splitlines(keepends=False)
    sections: list[Section] = []
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
        sections.append(Section(title=title, path=path, level=level, content=section_text))

    for i, tok in enumerate(tokens):
        if tok.type != "heading_open":
            continue
        heading_level = int(tok.tag[1])
        title = _extract_heading_title(tokens, i)
        while breadcrumb and breadcrumb[-1][0] >= heading_level:
            breadcrumb.pop()
        breadcrumb.append((heading_level, title))
        if heading_level in heading_levels:
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
            sections.insert(0, Section(title=None, path=[], level=0, content=pre_lines))

    return sections


def _extract_heading_title(tokens: list[Token], heading_open_index: int) -> str:
    if heading_open_index + 1 < len(tokens):
        inline_tok = tokens[heading_open_index + 1]
        if inline_tok.type == "inline" and inline_tok.content:
            return inline_tok.content.strip()
    return ""


def scan_fences(lines: list[str]) -> list[tuple[int, int]]:
    """Repère les blocs de code fence (``` ou ~~~) → liste de (start, end_exclusif)."""
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


def split_blocks(text: str) -> list[Block]:
    """Découpe `text` en blocs logiques en préservant les fences de code.

    Les régions hors fence sont découpées sur ligne vide (paragraphes, blocs
    prose) ; chaque fence devient un `Block` **atomique** — jamais fusionné ni
    shreddé par le normaliseur (ADR 0001 §3). Blocs vides éliminés.
    """
    lines = text.splitlines(keepends=False)
    fence_ranges = scan_fences(lines)
    blocks: list[Block] = []
    cursor = 0
    for fence_start, fence_end in fence_ranges:
        if cursor < fence_start:
            blocks.extend(_split_prose("\n".join(lines[cursor:fence_start])))
        fence_text = "\n".join(lines[fence_start:fence_end])
        if fence_text.strip():
            blocks.append(Block(text=fence_text, atomic=True))
        cursor = fence_end
    if cursor < len(lines):
        blocks.extend(_split_prose("\n".join(lines[cursor:])))
    return blocks


def _split_prose(text: str) -> list[Block]:
    return [Block.prose(p.strip()) for p in text.split("\n\n") if p.strip()]
