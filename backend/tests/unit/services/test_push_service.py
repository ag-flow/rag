from __future__ import annotations

import pytest

from rag.api.errors import InvalidPath
from rag.services.push import normalize_path


def test_normalize_backslash() -> None:
    assert normalize_path("docs\\sub\\foo.md") == "docs/sub/foo.md"


def test_normalize_rejects_traversal() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/../bar")
    assert exc.value.args[0] == "path_traversal_forbidden"


def test_normalize_rejects_absolute() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("/abs/path")


def test_normalize_rejects_nul() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("fo\x00o")


def test_normalize_valid_path() -> None:
    assert normalize_path("generated/docker-analysis.md") == "generated/docker-analysis.md"
