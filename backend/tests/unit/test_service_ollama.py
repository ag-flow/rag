from __future__ import annotations

import pytest

from rag.indexer.providers.services.ollama import OllamaService


def test_batch_size_is_one() -> None:
    assert OllamaService.batch_size == 1


def test_embeddings_path_is_empty() -> None:
    assert OllamaService.embeddings_path == ""


def test_document_payload_takes_first_text() -> None:
    svc = OllamaService()
    payload = svc.build_document_payload(["seul texte"], "qwen2.5-coder:14b")
    assert payload == {"model": "qwen2.5-coder:14b", "input": "seul texte"}


def test_query_payload_is_string() -> None:
    svc = OllamaService()
    payload = svc.build_query_payload("ma requête", "qwen2.5-coder:14b")
    assert payload == {"model": "qwen2.5-coder:14b", "input": "ma requête"}


def test_parse_response_returns_single_vector() -> None:
    svc = OllamaService()
    data = {"embeddings": [[0.1, 0.2, 0.3]]}
    result = svc.parse_response(data)
    assert result == [[0.1, 0.2, 0.3]]


def test_parse_response_missing_embeddings_raises() -> None:
    svc = OllamaService()
    with pytest.raises(RuntimeError, match="embeddings"):
        svc.parse_response({"embeddings": []})
