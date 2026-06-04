from __future__ import annotations

from rag.indexer.providers.services.voyage import VoyageService


def test_batch_size() -> None:
    assert VoyageService.batch_size == 128


def test_embeddings_path() -> None:
    assert VoyageService.embeddings_path == "/embeddings"


def test_document_payload_has_input_type_document() -> None:
    svc = VoyageService()
    payload = svc.build_document_payload(["doc1", "doc2"], "voyage-4")
    assert payload == {"model": "voyage-4", "input": ["doc1", "doc2"], "input_type": "document"}


def test_query_payload_has_input_type_query() -> None:
    svc = VoyageService()
    payload = svc.build_query_payload("ma requête", "voyage-4")
    assert payload == {"model": "voyage-4", "input": ["ma requête"], "input_type": "query"}


def test_parse_response_same_as_openai_compatible() -> None:
    svc = VoyageService()
    data = {"data": [{"index": 0, "embedding": [0.1, 0.2]}, {"index": 1, "embedding": [0.3, 0.4]}]}
    result = svc.parse_response(data)
    assert result == [[0.1, 0.2], [0.3, 0.4]]
