from __future__ import annotations

from typing import Any

from rag.indexer.chunking.cleaner import (
    CleaningLegacyChunkerWrapper,
    CleaningOptions,
)
from rag.indexer.chunking.markdown import MarkdownChunker
from rag.indexer.chunking.paragraph import ParagraphChunker
from rag.indexer.chunking.protocol import ChunkerProtocol

_CLEANING_KEYS = ("clean_content", "strip_separators", "strip_boilerplate", "strip_html")


def _extract_cleaning_options(extras: dict[str, Any]) -> CleaningOptions:
    """Construit les `CleaningOptions` depuis `extras` (clés absentes → False)."""
    return CleaningOptions(
        clean_content=bool(extras.get("clean_content", False)),
        strip_separators=bool(extras.get("strip_separators", False)),
        strip_boilerplate=bool(extras.get("strip_boilerplate", False)),
        strip_html=bool(extras.get("strip_html", False)),
    )


def make_chunker(
    *,
    strategy: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> ChunkerProtocol:
    """Construit un chunker selon la stratégie configurée.

    `extras` est un dict opaque : il peut porter les options de nettoyage
    booléennes (`clean_content`, `strip_separators`, `strip_boilerplate`,
    `strip_html`, toutes False par défaut) pour toute stratégie, plus
    `{heading_levels: int[]}` (default [1, 2]) pour 'markdown'. Le nettoyage
    est appliqué avant découpage via `CleaningLegacyChunkerWrapper`.

    Lève `ValueError` si la stratégie est inconnue ou si les extras sont
    invalides pour la stratégie choisie.
    """
    cleaning = _extract_cleaning_options(extras)
    strategy_extras = {k: v for k, v in extras.items() if k not in _CLEANING_KEYS}

    if strategy == "paragraph":
        if strategy_extras:
            raise ValueError(
                f"paragraph strategy does not accept extras (got {strategy_extras!r})"
            )
        base: ChunkerProtocol = ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    elif strategy == "markdown":
        base = _make_markdown_chunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
            extras=strategy_extras,
        )
    else:
        raise ValueError(f"unknown chunking strategy: {strategy}")

    if cleaning.any_enabled:
        return CleaningLegacyChunkerWrapper(base, cleaning)
    return base


def _make_markdown_chunker(
    *,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    extras: dict[str, Any],
) -> MarkdownChunker:
    """Construit un MarkdownChunker. Validation défensive des extras
    (déjà fait au niveau Pydantic, mais le factory peut être appelé hors
    API ex: tests). `extras` ici est déjà purgé des clés de nettoyage.
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
