from __future__ import annotations

from typing import Any

from rag.indexer.chunking.markdown import MarkdownChunker
from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import ChunkerProtocol


def make_chunker(
    *,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkerProtocol:
    """Construit un chunker selon la stratégie configurée.

    `extras` est un dict opaque réservé aux stratégies qui en ont besoin ;
    doit être vide pour 'paragraph', accepte {heading_levels: int[]} pour
    'markdown' (default [1, 2]).

    Lève `ValueError` si la stratégie est inconnue ou si les extras sont
    invalides pour la stratégie choisie.
    """
    if strategy == "paragraph":
        if extras:
            raise ValueError(f"paragraph strategy does not accept extras (got {extras!r})")
        return ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    if strategy == "markdown":
        return _make_markdown_chunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
            extras=extras,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")


def _make_markdown_chunker(
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> MarkdownChunker:
    """Construit un MarkdownChunker. Validation défensive des extras
    (déjà fait au niveau Pydantic, mais le factory peut être appelé hors
    API ex: tests).
    """
    allowed = {"heading_levels"}
    unknown = set(extras.keys()) - allowed
    if unknown:
        raise ValueError(f"markdown strategy unknown extras keys: {unknown}")
    heading_levels = extras.get("heading_levels", [1, 2])
    return MarkdownChunker(
        max_chars=max_chars,
        min_chars=min_chars,
        overlap_chars=overlap_chars,
        heading_levels=tuple(heading_levels),
    )
