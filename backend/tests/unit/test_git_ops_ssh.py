from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from rag.sync.git_ops import clone, pull


@pytest.mark.asyncio
async def test_clone_ssh_passes_git_ssh_command(tmp_path: Path) -> None:
    captured_env: dict = {}

    async def fake_run(args, *, cwd=None, error_cls=RuntimeError,
                       error_prefix="", extra_env=None):
        if extra_env:
            captured_env.update(extra_env)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=fake_run):
        dest = tmp_path / "repo"
        dest.mkdir()
        await clone(
            url="git@github.com:org/repo.git",
            branch="main",
            token=None,
            dest=dest,
            ssh_key="-----BEGIN OPENSSH PRIVATE KEY-----\nfake\n-----END OPENSSH PRIVATE KEY-----\n",
            ssh_username="git",
        )

    assert "GIT_SSH_COMMAND" in captured_env
    assert "StrictHostKeyChecking=no" in captured_env["GIT_SSH_COMMAND"]
    assert "BatchMode=yes" in captured_env["GIT_SSH_COMMAND"]


@pytest.mark.asyncio
async def test_clone_ssh_temp_file_cleaned_up(tmp_path: Path) -> None:
    created_paths: list[str] = []

    async def tracking_run(args, *, cwd=None, error_cls=RuntimeError,
                           error_prefix="", extra_env=None):
        if extra_env and "GIT_SSH_COMMAND" in extra_env:
            cmd = extra_env["GIT_SSH_COMMAND"]
            for part in cmd.split():
                if part.endswith(".pem"):
                    created_paths.append(part)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=tracking_run):
        dest = tmp_path / "repo2"
        dest.mkdir()
        await clone(
            url="git@github.com:org/repo.git",
            branch="main",
            token=None,
            dest=dest,
            ssh_key="fake_key_content",
            ssh_username="git",
        )

    assert len(created_paths) == 1
    assert not os.path.exists(created_paths[0])


@pytest.mark.asyncio
async def test_clone_without_ssh_uses_token_url(tmp_path: Path) -> None:
    captured_args: list = []

    async def fake_run(args, *, cwd=None, error_cls=RuntimeError,
                       error_prefix="", extra_env=None):
        captured_args.extend(args)
        return ("", "")

    with patch("rag.sync.git_ops._run_git", side_effect=fake_run):
        dest = tmp_path / "repo3"
        dest.mkdir()
        await clone(
            url="https://github.com/org/repo.git",
            branch="main",
            token="mytoken",
            dest=dest,
        )

    url_with_token = next((a for a in captured_args if "x-access-token" in a), None)
    assert url_with_token is not None
