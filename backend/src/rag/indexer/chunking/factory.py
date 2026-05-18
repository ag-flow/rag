from __future__ import annotations

from typing import Any

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
    if strategy == "paragraph":
        if extras:
            raise ValueError(f"paragraph strategy does not accept extras (got {extras!r})")
        return ParagraphChunker(
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
        )
    raise ValueError(f"unknown chunking strategy: {strategy}")
