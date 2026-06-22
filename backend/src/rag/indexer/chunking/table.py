from __future__ import annotations

from typing import Any

from rag.indexer.chunking.errors import ChunkTooLargeError
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, ParentSection
from rag.indexer.chunking.tokens import TokenEstimator

_TABLE_KEY = "(table)"
_SEP_CHARS = set("|:- ")


class TableChunker:
    """Stratégie tabulaire structure-aware (CSV/TSV/table Markdown pleine page).

    Parent = table entière (renvoyée au LLM). Enfants = en-tête répété + groupe
    de lignes, jamais de char-split (corrige le déchiquetage des tables passées
    en prose). Le groupe est borné par `max_rows_per_chunk` ET par
    `child_target_tokens` ; une ligne unique dépassant le plafond dur lève
    `ChunkTooLargeError` (pas de troncature silencieuse).
    """

    def __init__(
        self,
        *,
        estimator: TokenEstimator,
        bounds: TokenBounds,
        max_rows_per_chunk: int,
    ) -> None:
        if max_rows_per_chunk < 1:
            raise ValueError(f"max_rows_per_chunk must be >= 1, got {max_rows_per_chunk}")
        if bounds.child_target_tokens <= 0:
            raise ValueError("child_target_tokens must be > 0")
        if bounds.child_target_tokens > bounds.hard_ceiling_tokens:
            raise ValueError("child_target_tokens must be <= hard_ceiling_tokens")
        self._est = estimator
        self._b = bounds
        self._max_rows = max_rows_per_chunk

    def chunk(self, content: str) -> ChunkedDocument:
        lines = [ln for ln in content.splitlines() if ln.strip()]
        if not lines:
            return ChunkedDocument(parents=[], children=[])

        is_md = self._is_markdown_table(lines)
        header_lines = lines[:2] if is_md else lines[:1]
        data_lines = lines[2:] if is_md else lines[1:]

        meta: dict[str, Any] = {
            "section_title": None,
            "section_path": [],
            "heading_level": 0,
            "table_format": "markdown" if is_md else "delimited",
        }
        parent = ParentSection(section_key=_TABLE_KEY, content=content, metadata=meta)
        children = [
            ChildChunk(
                embed_text=self._render_child(header_lines, group),
                parent_key=_TABLE_KEY,
                metadata=meta,
            )
            for group in self._group_rows(header_lines, data_lines)
        ]
        return ChunkedDocument(parents=[parent], children=children)

    def _group_rows(self, header_lines: list[str], data_lines: list[str]) -> list[list[str]]:
        if not data_lines:
            return [[]]  # en-tête seul → un enfant porteur de l'en-tête
        groups: list[list[str]] = []
        group: list[str] = []
        for row in data_lines:
            candidate_tokens = self._est.estimate(self._join(header_lines, [*group, row]))
            over_target = candidate_tokens > self._b.child_target_tokens
            if group and (len(group) >= self._max_rows or over_target):
                groups.append(group)
                group = [row]
            else:
                group.append(row)
        if group:
            groups.append(group)
        return groups

    def _render_child(self, header_lines: list[str], group: list[str]) -> str:
        text = self._join(header_lines, group)
        estimated = self._est.estimate(text)
        if estimated > self._b.hard_ceiling_tokens:
            raise ChunkTooLargeError(
                estimated_tokens=estimated,
                hard_ceiling_tokens=self._b.hard_ceiling_tokens,
            )
        return text

    @staticmethod
    def _join(header_lines: list[str], group: list[str]) -> str:
        return "\n".join([*header_lines, *group])

    @staticmethod
    def _is_markdown_table(lines: list[str]) -> bool:
        if len(lines) < 2:
            return False
        sep = lines[1].strip()
        return bool(sep) and "-" in sep and set(sep) <= _SEP_CHARS
