from __future__ import annotations

from rag.indexer.providers.platforms.ollama import OllamaPlatform


def test_auth_headers_empty() -> None:
    p = OllamaPlatform("http://localhost:11434")
    assert p.auth_headers() == {}


def test_url_ignores_path_and_uses_api_embed() -> None:
    p = OllamaPlatform("http://localhost:11434")
    assert p.url("/embeddings") == "http://localhost:11434/api/embed"
    assert p.url("") == "http://localhost:11434/api/embed"


def test_url_strips_trailing_slash_from_base() -> None:
    p = OllamaPlatform("http://localhost:11434/")
    assert p.url("") == "http://localhost:11434/api/embed"


def test_modify_payload_is_identity() -> None:
    p = OllamaPlatform("http://localhost:11434")
    payload = {"model": "x", "input": "hello"}
    assert p.modify_payload(payload) == payload


def test_validate_auth_never_raises() -> None:
    p = OllamaPlatform("http://localhost:11434")
    p.validate_auth()  # pas d'exception
