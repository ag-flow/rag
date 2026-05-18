from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class Chunk:
    """Un chunk produit par un chunker. `metadata` est vide pour ParagraphChunker."""

    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


class ChunkerProtocol(Protocol):
    def chunk(self, content: str) -> list[Chunk]: ...
