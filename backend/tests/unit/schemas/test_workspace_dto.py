from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.workspace import PushRequest


def test_push_request_accepts_valid_payload() -> None:
    r = PushRequest(path="docs/foo.md", content="# Hello\n")
    assert r.path == "docs/foo.md"
    assert r.content == "# Hello\n"


def test_push_request_rejects_empty_path() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="", content="x")


def test_push_request_rejects_empty_content() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="ok.md", content="")


def test_push_request_accepts_content_at_exactly_5mb() -> None:
    content = "a" * (5 * 1024 * 1024)
    r = PushRequest(path="big.md", content=content)
    assert len(r.content) == 5 * 1024 * 1024


def test_push_request_rejects_content_above_5mb() -> None:
    content = "a" * (5 * 1024 * 1024 + 1)
    with pytest.raises(ValidationError) as exc:
        PushRequest(path="too_big.md", content=content)
    assert "content_too_large" in str(exc.value)


def test_push_request_counts_utf8_bytes_not_chars_for_size() -> None:
    # 'é' = 2 bytes UTF-8. 2_750_000 caractères = 5_500_000 bytes > 5 MB.
    content = "é" * (2_750_000)
    with pytest.raises(ValidationError):
        PushRequest(path="utf.md", content=content)


def test_push_request_rejects_path_above_1024_chars() -> None:
    with pytest.raises(ValidationError):
        PushRequest(path="a" * 1025, content="x")
