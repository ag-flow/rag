from __future__ import annotations

import math
from typing import Any

import structlog

from rag.indexer.chunking.code_chunker import CodeChunker
from rag.indexer.chunking.code_parser import UnsupportedLanguageError
from rag.indexer.chunking.data_chunker import DataChunker
from rag.indexer.chunking.markdown_deep import MarkdownDeepChunker
from rag.indexer.chunking.normalizer import TokenBounds
from rag.indexer.chunking.structured import StructuredChunkerProtocol
from rag.indexer.chunking.table import TableChunker
from rag.indexer.chunking.tokens import TokenEstimator

log = structlog.get_logger(__name__)

_PROSE_KEYS = {
    "child_target_tokens",
    "floor_tokens",
    "overlap_tokens",
    "breadcrumb_depth",
    "heading_levels",
}
_CODE_KEYS = {"child_target_tokens", "floor_tokens", "overlap_tokens", "breadcrumb_depth"}
_TABLE_KEYS = {"child_target_tokens", "max_rows_per_chunk"}
_ALLOWED: dict[str, set[str]] = {
    "prose": _PROSE_KEYS,
    "markdown": _PROSE_KEYS,
    "code": _CODE_KEYS,
    "data": _CODE_KEYS,
    "table": _TABLE_KEYS,
}

_DEFAULT_TARGET = 384
_DEFAULT_FLOOR = 64
_DEFAULT_OVERLAP = 64
_DEFAULT_DEPTH = -1
_DEFAULT_HEADING_LEVELS = (1, 2)
_DEFAULT_MAX_ROWS = 50


def make_structured_chunker(
    *,
    algo: str,
    params: dict[str, Any],
    estimator: TokenEstimator,
    provider_max_input_tokens: int,
    safety_factor: float = 0.8,
    language: str | None = None,
) -> StructuredChunkerProtocol:
    """Construit un chunker structure-aware depuis (algo + params nommés).

    `provider_max_input_tokens` est la source de vérité (ADR 0001 §3) : le
    plafond dur = ``floor(safety_factor * provider_max_input_tokens)``. Le
    `child_target_tokens` demandé est clampé sous ce plafond. Pour l'algo
    `code`, `language` (tree-sitter) est requis ; s'il est absent ou non
    supporté, on bascule gracieusement vers `prose`. Lève `ValueError` sur algo
    ou param inconnu.
    """
    if algo not in _ALLOWED:
        raise ValueError(f"unknown chunking algo: {algo!r}")
    unknown = set(params) - _ALLOWED[algo]
    if unknown:
        raise ValueError(f"unknown params for algo {algo!r}: {sorted(unknown)}")
    if provider_max_input_tokens <= 0:
        raise ValueError("provider_max_input_tokens must be > 0")
    if not 0 < safety_factor <= 1:
        raise ValueError("safety_factor must be in (0, 1]")

    hard = max(1, math.floor(safety_factor * provider_max_input_tokens))
    target = max(1, min(int(params.get("child_target_tokens", _DEFAULT_TARGET)), hard))

    if algo == "table":
        return TableChunker(
            estimator=estimator,
            bounds=TokenBounds(target, 0, 0, hard),
            max_rows_per_chunk=int(params.get("max_rows_per_chunk", _DEFAULT_MAX_ROWS)),
        )

    bounds = TokenBounds(
        child_target_tokens=target,
        floor_tokens=min(int(params.get("floor_tokens", _DEFAULT_FLOOR)), target),
        overlap_tokens=min(int(params.get("overlap_tokens", _DEFAULT_OVERLAP)), target - 1),
        hard_ceiling_tokens=hard,
    )
    depth = int(params.get("breadcrumb_depth", _DEFAULT_DEPTH))

    if algo in ("code", "data"):
        chunker = _try_treesitter_chunker(algo, language, estimator, bounds, depth)
        if chunker is not None:
            return chunker
        # fallback gracieux : langage non supporté → prose (borné en tokens)

    heading_levels = tuple(params.get("heading_levels", _DEFAULT_HEADING_LEVELS))
    return MarkdownDeepChunker(
        estimator=estimator,
        bounds=bounds,
        breadcrumb_depth=depth,
        heading_levels=heading_levels,
    )


def _try_treesitter_chunker(
    algo: str,
    language: str | None,
    estimator: TokenEstimator,
    bounds: TokenBounds,
    depth: int,
) -> StructuredChunkerProtocol | None:
    if not language:
        log.info("structured_factory.no_language_fallback_prose", algo=algo)
        return None
    builder = DataChunker if algo == "data" else CodeChunker
    try:
        return builder(
            language=language, estimator=estimator, bounds=bounds, breadcrumb_depth=depth
        )
    except UnsupportedLanguageError:
        log.info("structured_factory.unsupported_fallback_prose", algo=algo, language=language)
        return None
