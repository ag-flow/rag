from __future__ import annotations

import pytest

from rag.indexer.providers.platforms.bearer import BearerPlatform
from rag.indexer.providers.protocol import EmbeddingAuthError


def test_auth_headers_bearer() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-test")
    assert p.auth_headers() == {"Authorization": "Bearer sk-test"}


def test_url_appends_path() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-test")
    assert p.url("/embeddings") == "https://api.openai.com/v1/embeddings"


def test_url_strips_trailing_slash_from_base() -> None:
    p = BearerPlatform("https://api.openai.com/v1/", "sk-test")
    assert p.url("/embeddings") == "https://api.openai.com/v1/embeddings"


def test_url_empty_path_returns_base() -> None:
    p = BearerPlatform("https://example.com/full/path", "key")
    assert p.url("") == "https://example.com/full/path"


def test_modify_payload_is_identity() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "key")
    payload = {"model": "x", "input": ["a"]}
    assert p.modify_payload(payload) == payload


def test_validate_auth_raises_when_key_none() -> None:
    p = BearerPlatform("https://api.openai.com/v1", None)
    with pytest.raises(EmbeddingAuthError):
        p.validate_auth()


def test_validate_auth_passes_when_key_set() -> None:
    p = BearerPlatform("https://api.openai.com/v1", "sk-key")
    p.validate_auth()  # ne lève pas
