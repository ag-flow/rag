from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import clone, list_all_files
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_list_all_files_returns_tracked_files(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(
        tmp_path,
        {"README.md": "x", "docs/a.md": "y", "src/b.py": "z"},
    )
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    files = await list_all_files(dest)
    assert sorted(files) == ["README.md", "docs/a.md", "src/b.py"]


@pytest.mark.asyncio
async def test_list_all_files_excludes_untracked(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "x"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    # Fichier non tracké : ne doit pas apparaître
    (dest / "untracked.md").write_text("u")

    files = await list_all_files(dest)
    assert files == ["a.md"]
