from __future__ import annotations

from collections import Counter
from typing import Any

from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.code_parser import CodeNode, CodeParser
from rag.indexer.chunking.normalizer import TokenBounds, TokenNormalizer
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, ParentSection
from rag.indexer.chunking.tokens import TokenEstimator

_ROOT_KEY = "(root)"
_PAIR_KINDS = frozenset({"pair", "block_mapping_pair", "table"})


class DataChunker:
    """Stratégie données structurées (JSON / YAML / TOML) via tree-sitter.

    Chaque clé de premier niveau devient une unité (parent), avec son nom comme
    breadcrumb. À défaut de structure clé-valeur reconnue, le document entier
    devient une unité unique (bornée en tokens). Pas de char-split.
    """

    def __init__(
        self,
        *,
        language: str,
        estimator: TokenEstimator,
        bounds: TokenBounds,
        breadcrumb_depth: int,
    ) -> None:
        self._parser = CodeParser(language)
        self._normalizer = TokenNormalizer(estimator, bounds)
        self._depth = breadcrumb_depth

    def chunk(self, content: str) -> ChunkedDocument:
        if not content.strip():
            return ChunkedDocument(parents=[], children=[])

        root = self._parser.parse(content)
        pairs = _top_level_pairs(root)
        units: list[tuple[list[str], str]] = (
            [([_pair_key(p)], p.text) for p in pairs] if pairs else [([], content)]
        )

        parents: list[ParentSection] = []
        children: list[ChildChunk] = []
        seen: Counter[str] = Counter()
        for scope, text in units:
            key = _unit_key(scope, seen)
            meta: dict[str, Any] = {"scope": scope, "section_title": "/".join(scope)}
            parents.append(ParentSection(section_key=key, content=text, metadata=meta))
            for piece in self._normalizer.normalize(_split_lines_blocks(text)):
                children.append(
                    ChildChunk(
                        embed_text=prepend_breadcrumb(piece, scope, depth=self._depth),
                        parent_key=key,
                        metadata=meta,
                    )
                )
        return ChunkedDocument(parents=parents, children=children)


def _top_level_pairs(node: CodeNode) -> list[CodeNode]:
    """Ensemble de paires clé-valeur le moins profond (descend dans les
    wrappers document/object/mapping)."""
    pairs = [c for c in node.named_children if c.kind in _PAIR_KINDS]
    if pairs:
        return pairs
    for child in node.named_children:
        found = _top_level_pairs(child)
        if found:
            return found
    return []


def _pair_key(pair: CodeNode) -> str:
    key_node = pair.child_field("key")
    if key_node is None and pair.named_children:
        key_node = pair.named_children[0]
    if key_node is None:
        return pair.kind
    return key_node.text.strip().strip("\"'")


def _unit_key(scope: list[str], seen: Counter[str]) -> str:
    base = "/".join(scope) if scope else _ROOT_KEY
    seen[base] += 1
    occurrence = seen[base]
    return base if occurrence == 1 else f"{base}#{occurrence}"


def _split_lines_blocks(text: str) -> list[str]:
    blocks: list[str] = []
    current: list[str] = []
    for line in text.splitlines():
        if line.strip():
            current.append(line)
        elif current:
            blocks.append("\n".join(current))
            current = []
    if current:
        blocks.append("\n".join(current))
    return blocks
