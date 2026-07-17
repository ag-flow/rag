from __future__ import annotations

import re

from rag.indexer.chunking._sections import scan_fences
from rag.indexer.chunking.regions import REGION_TYPES, Region

_HEADING_RE = re.compile(r"^ {0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_TABLE_DELIMITER_RE = re.compile(r"^ {0,3}\|?(?:\s*:?-+:?\s*\|)*\s*:?-+:?\s*\|?\s*$")
_HTML_BLOCK_START_RE = re.compile(r"^ {0,3}<[a-zA-Z!/?]")
_FRONTMATTER_CLOSERS = ("---", "...")


class MarkdownRegionParser:
    """Segmente un document markdown en régions typées (passe 1 pure).

    Réutilise la détection de fences de `_sections.scan_fences` (même règle
    CommonMark de fermeture) et le suivi de titres ATX. Ne découpe pas, ne
    normalise pas : chaque ligne du source appartient à exactement une région.
    """

    slug = "markdown"
    region_types = REGION_TYPES

    def parse(self, content: str) -> list[Region]:
        if not content:
            return []
        return _Walker(content.splitlines(keepends=True)).walk()


class _Walker:
    """Parcours ligne à ligne : fences > tables > blocs HTML > prose.

    La prose est le résidu — elle absorbe titres et lignes vides, garantissant
    la couverture totale du source (propriété de reconstruction).
    """

    def __init__(self, lines: list[str]) -> None:
        self._lines = lines
        self._regions: list[Region] = []
        self._breadcrumb: list[tuple[int, str]] = []
        self._prose_start: int | None = None
        self._prose_path: list[str] = []
        self._fences: dict[int, int] = {}

    def walk(self) -> list[Region]:
        i = self._emit_frontmatter()
        self._fences = {start + i: end + i for start, end in scan_fences(self._lines[i:])}
        while i < len(self._lines):
            i = self._step(i)
        self._flush_prose(len(self._lines))
        return self._regions

    def _step(self, i: int) -> int:
        if i in self._fences:
            return self._emit_fence(i)
        if self._table_starts_at(i):
            return self._emit_table(i)
        if self._html_block_starts_at(i):
            return self._emit_html(i)
        if self._prose_start is None:
            self._prose_start = i
            self._prose_path = self._current_path()
        self._track_heading(self._lines[i])
        return i + 1

    # -- émission des régions -------------------------------------------------

    def _emit_frontmatter(self) -> int:
        end = _frontmatter_end(self._lines)
        if end is None:
            return 0
        self._append("frontmatter", None, 0, end, [])
        return end

    def _emit_fence(self, start: int) -> int:
        end = self._fences[start]
        self._flush_prose(start)
        self._append("code_fence", _fence_qualifier(self._lines[start]), start, end)
        return end

    def _emit_table(self, start: int) -> int:
        end = start + 2
        while end < len(self._lines) and end not in self._fences:
            line = self._lines[end]
            if not line.strip() or "|" not in line:
                break
            end += 1
        self._flush_prose(start)
        self._append("table", None, start, end)
        return end

    def _emit_html(self, start: int) -> int:
        end = start + 1
        while end < len(self._lines) and end not in self._fences:
            if not self._lines[end].strip():
                break
            end += 1
        self._flush_prose(start)
        self._append("html_block", None, start, end)
        return end

    def _flush_prose(self, end: int) -> None:
        if self._prose_start is not None:
            self._append("prose", None, self._prose_start, end, self._prose_path)
            self._prose_start = None

    def _append(
        self,
        region_type: str,
        qualifier: str | None,
        start: int,
        end: int,
        heading_path: list[str] | None = None,
    ) -> None:
        path = self._current_path() if heading_path is None else heading_path
        self._regions.append(
            Region(
                type=region_type,
                qualifier=qualifier,
                content="".join(self._lines[start:end]),
                heading_path=path,
                start_line=start + 1,
                end_line=end,
            )
        )

    # -- détections locales ---------------------------------------------------

    def _table_starts_at(self, i: int) -> bool:
        header = self._lines[i]
        if "|" not in header or not header.strip() or i + 1 >= len(self._lines):
            return False
        delimiter = self._lines[i + 1]
        return "|" in delimiter and bool(_TABLE_DELIMITER_RE.match(delimiter.rstrip("\r\n")))

    def _html_block_starts_at(self, i: int) -> bool:
        if not _HTML_BLOCK_START_RE.match(self._lines[i]):
            return False
        return i == 0 or not self._lines[i - 1].strip()

    # -- breadcrumb -----------------------------------------------------------

    def _track_heading(self, line: str) -> None:
        match = _HEADING_RE.match(line.rstrip("\r\n"))
        if not match:
            return
        level = len(match.group(1))
        while self._breadcrumb and self._breadcrumb[-1][0] >= level:
            self._breadcrumb.pop()
        self._breadcrumb.append((level, match.group(2).strip()))

    def _current_path(self) -> list[str]:
        return [title for _, title in self._breadcrumb]


def _frontmatter_end(lines: list[str]) -> int | None:
    """Index (exclusif) de fin du frontmatter YAML de tête, sinon None."""
    if not lines or lines[0].rstrip("\r\n") != "---":
        return None
    for j in range(1, len(lines)):
        if lines[j].rstrip("\r\n") in _FRONTMATTER_CLOSERS:
            return j + 1
    return None


def _fence_qualifier(opening_line: str) -> str | None:
    """Premier mot de l'info-string de la fence ('mermaid', 'python'), sinon None."""
    stripped = opening_line.lstrip()
    info = stripped.lstrip(stripped[0]).strip()
    return info.split()[0] if info else None
