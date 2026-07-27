from __future__ import annotations

import pytest

from rag.globmatch import glob_match, most_specific_index, specificity


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("**/*.md", "a.md", True),
        ("**/*.md", "docs/a.md", True),
        ("**/*.md", "deep/path/a.md", True),
        ("**/*.md", "a.py", False),
        ("docs/**", "docs/a.md", True),
        ("docs/**", "a.md", False),
        ("backlog/**/*.md", "backlog/2026/tache.md", True),
        ("backlog/**/*.md", "backlog/tache.md", True),
        ("backlog/**/*.md", "docs/tache.md", False),
        ("datasets/*.csv", "datasets/ventes.csv", True),
        ("datasets/*.csv", "datasets/2026/ventes.csv", False),
        ("*.md", "a.md", True),
        ("*.md", "docs/a.md", False),
        ("**", "nimporte/quoi.txt", True),
    ],
)
def test_glob_match(pattern: str, path: str, expected: bool) -> None:
    assert glob_match(pattern, path) is expected


def test_specificity_orders_by_segments_then_length() -> None:
    assert specificity("backlog/**/*.md") > specificity("**/*.md")
    assert specificity("docs/api/*.md") > specificity("docs/**")
    assert specificity("*.markdown") > specificity("*.md")


def test_most_specific_index_picks_deepest_pattern() -> None:
    patterns = ["**/*.md", "backlog/**/*.md", "datasets/*.csv"]
    assert most_specific_index(patterns, "backlog/2026/t.md") == 1
    assert most_specific_index(patterns, "docs/guide.md") == 0
    assert most_specific_index(patterns, "datasets/ventes.csv") == 2
    assert most_specific_index(patterns, "src/main.py") is None


def test_most_specific_index_tie_keeps_first() -> None:
    # Égalité parfaite de spécificité → le premier de la séquence gagne
    # (l'appelant fournit l'ordre de création croissant).
    patterns = ["**/*.md", "**/*.m?"]
    assert most_specific_index(patterns, "a.md") == 0
