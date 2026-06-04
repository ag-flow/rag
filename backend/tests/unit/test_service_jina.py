# backend/tests/unit/test_service_jina.py
from __future__ import annotations

from rag.indexer.providers.services.jina import JinaService


def test_document_payload_has_task_retrieval_passage() -> None:
    svc = JinaService()
    payload = svc.build_document_payload(["doc1"], "jina-embeddings-v3")
    assert payload == {"model": "jina-embeddings-v3", "input": ["doc1"], "task": "retrieval.passage"}


def test_query_payload_has_task_retrieval_query() -> None:
    svc = JinaService()
    payload = svc.build_query_payload("question", "jina-embeddings-v3")
    assert payload == {"model": "jina-embeddings-v3", "input": ["question"], "task": "retrieval.query"}


def test_batch_size_and_path_inherited() -> None:
    svc = JinaService()
    assert svc.batch_size == 100
    assert svc.embeddings_path == "/embeddings"
