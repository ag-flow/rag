from __future__ import annotations

from functools import cached_property

from rag.indexer.chunking.errors import ChunkingError


class UnsupportedLanguageError(ChunkingError):
    """Le langage demandé n'est pas fourni par le binding tree-sitter."""

    def __init__(self, language: str) -> None:
        super().__init__(f"unsupported tree-sitter language: {language!r}")
        self.language = language


class CodeNode:
    """Vue propre et paresseuse d'un nœud tree-sitter.

    Isole l'API non standard du binding (tout est méthode, `kind`/`name` au lieu
    de `type`/champs) derrière une interface stable utilisée par le chunker.
    """

    def __init__(self, node: object, src: bytes) -> None:
        self._node = node
        self._src = src

    @cached_property
    def kind(self) -> str:
        return self._node.kind()  # type: ignore[attr-defined]

    @cached_property
    def name(self) -> str | None:
        name_node = self._node.child_by_field_name("name")  # type: ignore[attr-defined]
        if name_node is None:
            return None
        return self._src[name_node.start_byte() : name_node.end_byte()].decode(
            "utf-8", "replace"
        )

    @cached_property
    def start_line(self) -> int:
        return int(self._node.start_position().row)  # type: ignore[attr-defined]

    @cached_property
    def end_line(self) -> int:
        return int(self._node.end_position().row)  # type: ignore[attr-defined]

    @cached_property
    def text(self) -> str:
        return self._src[
            self._node.start_byte() : self._node.end_byte()  # type: ignore[attr-defined]
        ].decode("utf-8", "replace")

    @cached_property
    def has_error(self) -> bool:
        return bool(self._node.has_error())  # type: ignore[attr-defined]

    def child_field(self, field_name: str) -> CodeNode | None:
        """Nœud du champ nommé (`key`, `value`, …) ou None."""
        field_node = self._node.child_by_field_name(field_name)  # type: ignore[attr-defined]
        return CodeNode(field_node, self._src) if field_node is not None else None

    @cached_property
    def named_children(self) -> list[CodeNode]:
        node = self._node
        count = node.named_child_count()  # type: ignore[attr-defined]
        return [CodeNode(node.named_child(i), self._src) for i in range(count)]  # type: ignore[attr-defined]


class CodeParser:
    """Parse du code source via tree-sitter, exposé en `CodeNode`.

    Lève `UnsupportedLanguageError` si le langage n'existe pas dans le pack.
    """

    def __init__(self, language: str) -> None:
        try:
            from tree_sitter_language_pack import get_parser
        except ImportError as exc:  # pragma: no cover - dépendance optionnelle
            raise ChunkingError("tree-sitter-language-pack is not installed") from exc
        try:
            self._parser = get_parser(language)  # type: ignore[arg-type]
        except (LookupError, ValueError, KeyError, RuntimeError) as exc:
            raise UnsupportedLanguageError(language) from exc
        self._language = language

    def parse(self, source: str) -> CodeNode:
        src_bytes = source.encode("utf-8")
        tree = self._parser.parse(source)
        return CodeNode(tree.root_node(), src_bytes)
