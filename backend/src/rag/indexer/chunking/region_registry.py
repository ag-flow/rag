from __future__ import annotations

from rag.indexer.chunking.markdown_regions import MarkdownRegionParser
from rag.indexer.chunking.regions import RegionParser

_PARSERS: dict[str, RegionParser] = {parser.slug: parser for parser in (MarkdownRegionParser(),)}


def get_region_parser(slug: str) -> RegionParser:
    """Résout un parser de régions par slug (miroir code de `chunking_parsers`)."""
    parser = _PARSERS.get(slug)
    if parser is None:
        raise ValueError(f"unknown region parser: {slug!r}")
    return parser


def available_parsers() -> frozenset[str]:
    return frozenset(_PARSERS)
