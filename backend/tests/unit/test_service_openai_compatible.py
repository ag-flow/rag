from __future__ import annotations

from rag.indexer.providers.services.openai_compatible import OpenAICompatibleService


def test_batch_size() -> None:
    svc = OpenAICompatibleService()
    assert svc.batch_size == 100


def test_embeddings_path() -> None:
    svc = OpenAICompatibleService()
    assert svc.embeddings_path == "/embeddings"


def test_build_document_payload() -> None:
    svc = OpenAICompatibleService()
    payload = svc.build_document_payload(["hello", "world"], "text-embedding-3-small")
    assert payload == {"model": "text-embedding-3-small", "input": ["hello", "world"]}


def test_build_query_payload() -> None:
    svc = OpenAICompatibleService()
    payload = svc.build_query_payload("ma requête", "text-embedding-3-small")
    assert payload == {"model": "text-embedding-3-small", "input": ["ma requête"]}


def test_parse_response_sorted_by_index() -> None:
    svc = OpenAICompatibleService()
    data = {
        "data": [
            {"index": 1, "embedding": [0.2, 0.2]},
            {"index": 0, "embedding": [0.1, 0.1]},
        ]
    }
    result = svc.parse_response(data)
    assert result == [[0.1, 0.1], [0.2, 0.2]]


def test_parse_response_empty_data() -> None:
    svc = OpenAICompatibleService()
    assert svc.parse_response({"data": []}) == []
