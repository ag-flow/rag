from __future__ import annotations

from rag.schemas.sync import ChangeSet
from rag.sync.git_ops import filter_glob


def test_filter_glob_default_includes_everything() -> None:
    cs = ChangeSet(added=["a.md", "b.py"], modified=["c.json"], deleted=["d.png"])
    out = filter_glob(cs, include=["**/*"], exclude=[])
    assert out.added == ["a.md", "b.py"]
    assert out.modified == ["c.json"]
    assert out.deleted == ["d.png"]


def test_filter_glob_include_only_markdown() -> None:
    cs = ChangeSet(added=["a.md", "b.py"], modified=["docs/c.md"])
    out = filter_glob(cs, include=["**/*.md"], exclude=[])
    assert out.added == ["a.md"]
    assert out.modified == ["docs/c.md"]


def test_filter_glob_exclude_takes_priority() -> None:
    cs = ChangeSet(added=["a.md", "node_modules/x.md"], modified=[])
    out = filter_glob(cs, include=["**/*.md"], exclude=["node_modules/**"])
    assert out.added == ["a.md"]
    assert out.modified == []


def test_filter_glob_empty_changeset() -> None:
    cs = ChangeSet()
    out = filter_glob(cs, include=["**/*"], exclude=[])
    assert out.total_changed == 0


def test_filter_glob_exclude_nested_node_modules() -> None:
    """Régression : **/node_modules/** doit exclure les chemins imbriqués.

    Avant le fix (fnmatch desugaring), `node_modules/*` ne matchait que les
    chemins commençant par node_modules/ — les chemins comme
    tools/md2pdf/node_modules/... passaient le filtre.
    """
    cs = ChangeSet(
        added=[
            "tools/md2pdf/node_modules/smart-buffer/docs/ROADMAP.md",
            "tools/svg2pptx/node_modules/smart-buffer/docs/ROADMAP.md",
            "tools/md2pdf/node_modules/moment-mini/locale/locale.js",
            "docs/README.md",
            "guides/setup.md",
        ]
    )
    out = filter_glob(
        cs,
        include=["**/*.md", "docs/**"],
        exclude=["**/node_modules/**"],
    )
    # Seuls les .md hors node_modules doivent passer
    assert sorted(out.added) == ["docs/README.md", "guides/setup.md"]


def test_filter_glob_docs_pattern_does_not_leak_into_node_modules() -> None:
    """docs/** ne doit pas matcher tools/.../node_modules/.../docs/ROADMAP.md
    quand l'exclude **/node_modules/** est actif.
    """
    cs = ChangeSet(
        added=[
            "tools/md2pdf/node_modules/smart-buffer/docs/ROADMAP.md",
            "docs/ROADMAP.md",
        ]
    )
    out = filter_glob(
        cs,
        include=["docs/**"],
        exclude=["**/node_modules/**"],
    )
    assert out.added == ["docs/ROADMAP.md"]
