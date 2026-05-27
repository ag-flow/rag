from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import clone, diff_changes, head_commit, pull
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_diff_changes_added_modified_deleted(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(
        tmp_path,
        {"a.md": "v1", "b.md": "v1", "c.md": "v1"},
    )
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha_initial = await head_commit(dest)

    # Modif côté remote : a.md modifié, b.md supprimé, d.md ajouté
    work_remote = tmp_path / "work"
    sha_after = add_commit(
        work_remote,
        files={"a.md": "v2", "d.md": "v1"},
        deletes=["b.md"],
    )
    await pull(dest=dest, branch="main")

    changes = await diff_changes(dest=dest, from_commit=sha_initial, to_commit=sha_after)
    assert sorted(changes.added) == ["d.md"]
    assert sorted(changes.modified) == ["a.md"]
    assert sorted(changes.deleted) == ["b.md"]
