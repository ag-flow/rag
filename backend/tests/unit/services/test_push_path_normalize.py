from __future__ import annotations

import pytest

from rag.api.errors import InvalidPath
from rag.services.push import normalize_path


def test_happy_path_passthrough() -> None:
    assert normalize_path("docs/foo.md") == "docs/foo.md"


def test_windows_backslashes_normalized_to_forward() -> None:
    assert normalize_path("docs\\sub\\foo.md") == "docs/sub/foo.md"


def test_nul_byte_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo\x00bar")
    assert exc.value.reason == "path_contains_nul"


def test_absolute_path_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("/etc/passwd")
    assert exc.value.reason == "path_must_be_relative"


def test_traversal_segment_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/../bar")
    assert exc.value.reason == "path_traversal_forbidden"


def test_leading_traversal_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("../foo")
    assert exc.value.reason == "path_traversal_forbidden"


def test_trailing_traversal_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("foo/..")
    assert exc.value.reason == "path_traversal_forbidden"


def test_empty_after_normalization_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("")
    assert exc.value.reason == "path_invalid_length"


def test_above_1024_chars_rejected() -> None:
    with pytest.raises(InvalidPath) as exc:
        normalize_path("a" * 1025)
    assert exc.value.reason == "path_invalid_length"


def test_double_dot_inside_filename_accepted() -> None:
    # "foo/..bar" : "..bar" est un nom de fichier valide, pas un segment ..
    assert normalize_path("foo/..bar") == "foo/..bar"


def test_double_dot_at_segment_boundary_rejected() -> None:
    with pytest.raises(InvalidPath):
        normalize_path("a/../b")
