from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import detect_default_branch
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_detect_default_branch_main(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="main")
    assert await detect_default_branch(url=f"file://{bare}", token=None) == "main"


@pytest.mark.asyncio
async def test_detect_default_branch_master(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "x"}, default_branch="master")
    assert await detect_default_branch(url=f"file://{bare}", token=None) == "master"


@pytest.mark.asyncio
async def test_detect_default_branch_none_when_unreachable(tmp_path: Path) -> None:
    result = await detect_default_branch(
        url="https://example.invalid/x/y.git", token=None, deadline=5.0
    )
    assert result is None
