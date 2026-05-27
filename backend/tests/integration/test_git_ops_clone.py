from __future__ import annotations

from pathlib import Path

import pytest

from rag.sync.git_ops import GitCloneError, clone, sanitize_git_output
from tests.integration._git_fixture import make_bare_repo_with_commits


@pytest.mark.asyncio
async def test_clone_success_creates_git_dir(tmp_path: Path) -> None:
    bare = make_bare_repo_with_commits(tmp_path, {"README.md": "hello"})
    dest = tmp_path / "dest"
    await clone(url=f"file://{bare}", branch="main", token=None, dest=dest)
    assert (dest / ".git").is_dir()
    assert (dest / "README.md").read_text() == "hello"


@pytest.mark.asyncio
async def test_clone_failure_raises_with_sanitized_stderr(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    with pytest.raises(GitCloneError) as exc_info:
        await clone(
            url="https://x-access-token:secrettoken@example.invalid/x/y.git",
            branch="main",
            token="secrettoken",
            dest=dest,
        )
    # Le message d'erreur ne doit PAS contenir le token
    assert "secrettoken" not in str(exc_info.value)
    assert "***" in str(exc_info.value) or "git clone failed" in str(exc_info.value)


def test_sanitize_git_output_redacts_basic_auth() -> None:
    raw = "fatal: could not resolve https://x-access-token:ghp_abc@github.com/x/y.git"
    sanitized = sanitize_git_output(raw)
    assert "ghp_abc" not in sanitized
    assert "***" in sanitized


def test_sanitize_git_output_passes_through_when_no_secret() -> None:
    raw = "Cloning into 'dest'...\nFatal: not a git repository"
    sanitized = sanitize_git_output(raw)
    assert sanitized == raw
