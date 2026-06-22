from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from rag.indexer.chunking.breadcrumb import prepend_breadcrumb
from rag.indexer.chunking.code_parser import CodeNode, CodeParser
from rag.indexer.chunking.normalizer import TokenBounds, TokenNormalizer
from rag.indexer.chunking.structured import ChildChunk, ChunkedDocument, ParentSection
from rag.indexer.chunking.tokens import TokenEstimator

_MODULE_KEY = "(module)"


@dataclass(frozen=True)
class _LangConfig:
    def_kinds: frozenset[str]
    container_kinds: frozenset[str]


# Config curée. Langages absents → mode générique (un nœud nommé = une unité).
_CONFIG: dict[str, _LangConfig] = {
    "python": _LangConfig(frozenset({"function_definition"}), frozenset({"class_definition"})),
    "javascript": _LangConfig(
        frozenset({"function_declaration", "method_definition", "generator_function_declaration"}),
        frozenset({"class_declaration"}),
    ),
    "typescript": _LangConfig(
        frozenset({"function_declaration", "method_definition", "function_signature"}),
        frozenset({"class_declaration", "abstract_class_declaration", "interface_declaration"}),
    ),
    "tsx": _LangConfig(
        frozenset({"function_declaration", "method_definition", "function_signature"}),
        frozenset({"class_declaration", "abstract_class_declaration", "interface_declaration"}),
    ),
    "go": _LangConfig(
        frozenset({"function_declaration", "method_declaration"}), frozenset()
    ),
    "rust": _LangConfig(
        frozenset({"function_item"}),
        frozenset({"impl_item", "trait_item", "mod_item"}),
    ),
    "java": _LangConfig(
        frozenset({"method_declaration", "constructor_declaration"}),
        frozenset({"class_declaration", "interface_declaration", "enum_declaration"}),
    ),
    "c": _LangConfig(frozenset({"function_definition"}), frozenset()),
    "cpp": _LangConfig(
        frozenset({"function_definition"}),
        frozenset({"class_specifier", "struct_specifier"}),
    ),
}

_BLOCK_KINDS = frozenset(
    {"block", "class_body", "declaration_list", "statement_block", "field_declaration_list"}
)


@dataclass
class _Unit:
    scope: list[str]
    text: str


class CodeChunker:
    """Stratégie code structure-aware (tree-sitter) — small-to-big.

    Découpe par symboles : chaque fonction / méthode / classe devient une unité
    (parent). Les classes sont émises sous forme de « coquille » (corps des
    méthodes élidé) + une unité par méthode (breadcrumb = portée). Le code
    module-level (imports, statements) est coalescé en unités `(module)`. Les
    enfants sont bornés en tokens. Tree-sitter étant tolérant aux erreurs, le
    découpage reste best-effort sur du code partiellement invalide.
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
        self._cfg = _CONFIG.get(language)
        self._normalizer = TokenNormalizer(estimator, bounds)
        self._depth = breadcrumb_depth

    def chunk(self, content: str) -> ChunkedDocument:
        if not content.strip():
            return ChunkedDocument(parents=[], children=[])

        root = self._parser.parse(content)
        lines = content.splitlines()
        units = self._build_units(root, lines)
        if not units:
            units = [_Unit(scope=[], text=content)]

        parents: list[ParentSection] = []
        children: list[ChildChunk] = []
        seen: Counter[str] = Counter()
        for unit in units:
            key = self._unit_key(unit, seen)
            meta: dict[str, Any] = {"scope": unit.scope, "section_title": "/".join(unit.scope)}
            parents.append(ParentSection(section_key=key, content=unit.text, metadata=meta))
            for piece in self._normalizer.normalize(_split_code_blocks(unit.text)):
                children.append(
                    ChildChunk(
                        embed_text=prepend_breadcrumb(piece, unit.scope, depth=self._depth),
                        parent_key=key,
                        metadata=meta,
                    )
                )
        return ChunkedDocument(parents=parents, children=children)

    def _build_units(self, root: CodeNode, lines: list[str]) -> list[_Unit]:
        units: list[_Unit] = []
        pending: list[CodeNode] = []

        def flush() -> None:
            if not pending:
                return
            start, end = pending[0].start_line, pending[-1].end_line
            text = "\n".join(lines[start : end + 1])
            if text.strip():
                units.append(_Unit(scope=[], text=text))
            pending.clear()

        for node in root.named_children:
            if self._is_def(node):
                flush()
                units.append(_Unit(scope=[node.name or node.kind], text=node.text))
            elif self._is_container(node):
                flush()
                units.extend(self._container_units(node, lines))
            else:
                pending.append(node)
        flush()
        return units

    def _container_units(self, container: CodeNode, lines: list[str]) -> list[_Unit]:
        cname = container.name or container.kind
        members = self._members(container)
        if not members:
            return [_Unit(scope=[cname], text=container.text)]
        shell = _elide_members(lines, container, members)
        result = [_Unit(scope=[cname], text=shell)]
        result.extend(_Unit(scope=[cname, m.name or m.kind], text=m.text) for m in members)
        return result

    def _members(self, container: CodeNode) -> list[CodeNode]:
        out: list[CodeNode] = []
        for child in container.named_children:
            if self._is_def(child):
                out.append(child)
            elif _is_block(child.kind):
                out.extend(g for g in child.named_children if self._is_def(g))
        return out

    def _is_def(self, node: CodeNode) -> bool:
        if self._cfg is None:
            return node.name is not None
        return node.kind in self._cfg.def_kinds

    def _is_container(self, node: CodeNode) -> bool:
        if self._cfg is None:
            return False
        return node.kind in self._cfg.container_kinds

    @staticmethod
    def _unit_key(unit: _Unit, seen: Counter[str]) -> str:
        base = "/".join(unit.scope) if unit.scope else _MODULE_KEY
        seen[base] += 1
        occurrence = seen[base]
        return base if occurrence == 1 else f"{base}#{occurrence}"


def _is_block(kind: str) -> bool:
    return kind in _BLOCK_KINDS or kind.endswith(("_body", "_list")) or "block" in kind


def _elide_members(lines: list[str], container: CodeNode, members: list[CodeNode]) -> str:
    """Texte de la coquille de classe : corps des méthodes remplacés par un
    marqueur ``… <nom>`` (pas de duplication du corps dans la coquille)."""
    spans = sorted((m.start_line, m.end_line, m.name or m.kind) for m in members)
    shell: list[str] = []
    row = container.start_line
    idx = 0
    while row <= container.end_line:
        if idx < len(spans) and row == spans[idx][0]:
            _, end, name = spans[idx]
            indent = lines[row][: len(lines[row]) - len(lines[row].lstrip())]
            shell.append(f"{indent}… {name}")
            row = end + 1
            idx += 1
        else:
            shell.append(lines[row])
            row += 1
    return "\n".join(shell)


def _split_code_blocks(text: str) -> list[str]:
    """Découpe le code en blocs sur ligne vide, SANS retirer l'indentation
    (contrairement à la prose) — l'indentation est sémantique en code."""
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
