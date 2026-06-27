from __future__ import annotations

from typing import Any

from rag.indexer.chunking.factory import make_chunker
from rag.indexer.chunking.hashing import compute_chunk_hash
from rag.indexer.chunking.structured_factory import make_structured_chunker
from rag.indexer.chunking.tokens import HeuristicTokenEstimator

_PREVIEW = 160


def render_chunk_diff(
    content: str,
    *,
    legacy_strategy: str = "markdown",
    legacy_max_chars: int = 2000,
    legacy_min_chars: int = 200,
    legacy_overlap_chars: int = 200,
    legacy_extras: dict[str, Any] | None = None,
    structured_algo: str = "prose",
    structured_params: dict[str, Any] | None = None,
    structured_language: str | None = None,
    char_ratio: float = 4.0,
    provider_max_input_tokens: int = 8192,
) -> str:
    """Produit un rapport texte comparant le découpage legacy vs structured.

    Outil de non-régression (ADR 0001 §7 / mission Phase 3) : permet
    l'inspection humaine du diff de chunks AVANT bascule d'un workspace. Les
    deux chunkers sont purs → aucun appel DB/provider nécessaire.
    """
    estimator = HeuristicTokenEstimator(char_ratio=char_ratio)

    legacy = make_chunker(
        strategy=legacy_strategy,
        max_chars=legacy_max_chars,
        min_chars=legacy_min_chars,
        overlap_chars=legacy_overlap_chars,
        extras=legacy_extras or {},
    ).chunk(content)

    doc = make_structured_chunker(
        algo=structured_algo,
        params=structured_params or {},
        estimator=estimator,
        provider_max_input_tokens=provider_max_input_tokens,
        language=structured_language,
    ).chunk(content)

    lines: list[str] = ["# Chunk diff report", ""]
    lines.append(f"## LEGACY (strategy={legacy_strategy}, chunks={len(legacy)})")
    for i, chunk in enumerate(legacy):
        toks = estimator.estimate(chunk.content)
        lines.append(f"### chunk {i} [{len(chunk.content)} chars / ~{toks} tok]")
        lines.append(_preview(chunk.content))
    lines.append("")
    lines.append(
        f"## STRUCTURED (algo={structured_algo}, "
        f"parents={len(doc.parents)}, children={len(doc.children)})"
    )
    for parent in doc.parents:
        lines.append(f"### parent: {parent.section_key} [{len(parent.content)} chars]")
        lines.append(_preview(parent.content))
    for j, child in enumerate(doc.children):
        toks = estimator.estimate(child.embed_text)
        digest = compute_chunk_hash(child.embed_text)[:19]
        lines.append(f"#### child {j} [~{toks} tok] parent={child.parent_key} {digest}")
        lines.append(_preview(child.embed_text))
    return "\n".join(lines)


def _preview(text: str) -> str:
    flat = text.replace("\n", "⏎")
    return flat if len(flat) <= _PREVIEW else flat[:_PREVIEW] + "…"
