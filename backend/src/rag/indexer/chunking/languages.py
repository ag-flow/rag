from __future__ import annotations

from pathlib import PurePosixPath

# Extension → langage tree-sitter. Aligné sur les extensions de catégorie 'code'
# (migration 040). Les langages non couverts par le pack basculent en prose au
# niveau du factory (fallback gracieux).
_LANGUAGE_BY_EXTENSION: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".c": "c",
    ".h": "c",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".hpp": "cpp",
    ".rb": "ruby",
    ".php": "php",
    ".sql": "sql",
    ".sh": "bash",
    ".bash": "bash",
    ".css": "css",
    ".scss": "scss",
    # données structurées (catégorie 'data')
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
}


def language_for_path(path: str | None) -> str | None:
    """Retourne le langage tree-sitter pour `path`, ou None si non mappé."""
    if not path:
        return None
    return _LANGUAGE_BY_EXTENSION.get(PurePosixPath(path).suffix.lower())
