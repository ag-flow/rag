from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import GitPullError, clone, head_commit, pull
from tests.integration._git_fixture import add_commit, make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_head_commit_returns_sha_after_clone(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha = await head_commit(dest)
    assert len(sha) == 40
    assert all(c in "0123456789abcdef" for c in sha)


@pytest.mark.asyncio
async def test_pull_fetches_new_commit(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    sha_before = await head_commit(dest)

    work_remote = tmp_path / "work"
    sha_added = add_commit(work_remote, {"b.md": "v1"})

    await pull(dest=dest, branch="main")
    sha_after = await head_commit(dest)
    assert sha_after != sha_before
    assert sha_after == sha_added
    assert (dest / "b.md").exists()


@pytest.mark.asyncio
async def test_pull_resets_local_modifs(tmp_path: Path) -> None:
    """`pull` doit faire reset --hard pour garantir l'alignement avec remote."""
    bare = make_bare_repo_with_commits(tmp_path, {"a.md": "v1"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)

    # Modifie un fichier localement (simule corruption)
    (dest / "a.md").write_text("CORRUPTED")

    await pull(dest=dest, branch="main")
    assert (dest / "a.md").read_text() == "v1"  # reset


@pytest.mark.asyncio
async def test_pull_fails_on_invalid_path(tmp_path: Path) -> None:
    with pytest.raises(GitPullError):
        await pull(dest=tmp_path / "nonexistent", branch="main")
