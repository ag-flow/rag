from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from rag.services.sources import _resolve_branch_for_write


@pytest.mark.asyncio
async def test_keeps_explicit_branch_without_detection() -> None:
    config = {"url": "https://github.com/x/y", "branch": "develop"}
    with patch("rag.services.sources.detect_default_branch", AsyncMock()) as detect:
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "develop"
    assert warning is None
    detect.assert_not_called()


@pytest.mark.asyncio
async def test_detects_when_branch_empty() -> None:
    config = {"url": "https://github.com/x/y", "branch": ""}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="master")
    ):
        out, warning = await _resolve_branch_for_write(config, token="tok")
    assert out["branch"] == "master"
    assert warning is None


@pytest.mark.asyncio
async def test_detects_when_branch_absent() -> None:
    config = {"url": "https://github.com/x/y"}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="main")
    ):
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "main"
    assert warning is None


@pytest.mark.asyncio
async def test_fallback_main_with_warning_on_detection_failure() -> None:
    config = {"url": "https://github.com/x/y", "branch": ""}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value=None)
    ):
        out, warning = await _resolve_branch_for_write(config, token=None)
    assert out["branch"] == "main"
    assert warning is not None
    assert "main" in warning


@pytest.mark.asyncio
async def test_does_not_mutate_input_config() -> None:
    config = {"url": "https://github.com/x/y"}
    with patch(
        "rag.services.sources.detect_default_branch", AsyncMock(return_value="master")
    ):
        await _resolve_branch_for_write(config, token=None)
    assert "branch" not in config  # l'original n'est pas modifié
