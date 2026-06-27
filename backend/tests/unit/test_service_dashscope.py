# backend/tests/unit/test_service_dashscope.py
from __future__ import annotations

from rag.indexer.providers.services.dashscope import DashScopeService


def test_batch_size_is_25() -> None:
    assert DashScopeService.batch_size == 25


def test_embeddings_path_is_empty() -> None:
    assert DashScopeService.embeddings_path == ""


def test_document_payload_format() -> None:
    svc = DashScopeService()
    payload = svc.build_document_payload(["a", "b"], "text-embedding-v3")
    assert payload == {"model": "text-embedding-v3", "input": {"texts": ["a", "b"]}}


def test_query_payload_format() -> None:
    svc = DashScopeService()
    payload = svc.build_query_payload("question", "text-embedding-v3")
    assert payload == {"model": "text-embedding-v3", "input": {"texts": ["question"]}}


def test_parse_response_sorted_by_text_index() -> None:
    svc = DashScopeService()
    data = {
        "output": {
            "embeddings": [
                {"text_index": 1, "embedding": [0.2, 0.2]},
                {"text_index": 0, "embedding": [0.1, 0.1]},
            ]
        }
    }
    result = svc.parse_response(data)
    assert result == [[0.1, 0.1], [0.2, 0.2]]
