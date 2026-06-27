from __future__ import annotations

import pytest

from rag.indexer.providers.platforms.azure_openai import AzureOpenAIPlatform
from rag.indexer.providers.protocol import EmbeddingAuthError

_BASE = "https://myresource.openai.azure.com/openai/deployments/text-embedding-3-small"


def test_auth_header_is_api_key_not_bearer() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    headers = p.auth_headers()
    assert headers == {"api-key": "az-key"}
    assert "Authorization" not in headers


def test_url_appends_api_version() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    url = p.url("/embeddings")
    assert url == f"{_BASE}/embeddings?api-version=2024-02-01"


def test_modify_payload_strips_model() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    payload = {"model": "text-embedding-3-small", "input": ["hello"]}
    result = p.modify_payload(payload)
    assert result == {"input": ["hello"]}
    assert "model" not in result


def test_modify_payload_preserves_other_fields() -> None:
    p = AzureOpenAIPlatform(_BASE, "az-key")
    payload = {"model": "x", "input": ["a"], "input_type": "document"}
    result = p.modify_payload(payload)
    assert result == {"input": ["a"], "input_type": "document"}


def test_validate_auth_raises_when_key_none() -> None:
    p = AzureOpenAIPlatform(_BASE, None)
    with pytest.raises(EmbeddingAuthError):
        p.validate_auth()
