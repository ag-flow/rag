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
