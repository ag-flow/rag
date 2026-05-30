from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.sync.git_ops import list_remote_branches


@pytest.mark.asyncio
async def test_list_remote_branches_parses_heads() -> None:
    ls_remote_output = (
        "abc123\trefs/heads/main\n"
        "def456\trefs/heads/develop\n"
        "ghi789\trefs/heads/feature/auth\n"
    ).encode()

    fake_proc = MagicMock()
    fake_proc.returncode = 0
    fake_proc.communicate = AsyncMock(return_value=(ls_remote_output, b""))

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        result = await list_remote_branches(url="https://github.com/org/repo.git")

    assert result == ["develop", "feature/auth", "main"]


@pytest.mark.asyncio
async def test_list_remote_branches_returns_empty_on_error() -> None:
    fake_proc = MagicMock()
    fake_proc.returncode = 128
    fake_proc.communicate = AsyncMock(return_value=(b"", b"fatal: not found"))

    with patch("asyncio.create_subprocess_exec", return_value=fake_proc):
        result = await list_remote_branches(url="https://github.com/org/private.git")

    assert result == []


@pytest.mark.asyncio
async def test_list_remote_branches_returns_empty_on_timeout() -> None:
    async def slow_exec(*args, **kwargs):
        raise TimeoutError()

    with patch("asyncio.create_subprocess_exec", side_effect=slow_exec):
        result = await list_remote_branches(
            url="https://github.com/org/repo.git", deadline=0.001
        )

    assert result == []
