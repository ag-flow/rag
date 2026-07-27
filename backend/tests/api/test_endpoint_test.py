from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi.testclient import TestClient


def _allow_vault(admin_client: TestClient) -> str:
    """Autorise l'accès coffre pour la route (stub get_by_id) → vault_id."""
    vault = MagicMock()
    vault.id = uuid4()
    vault.owner_id = None  # coffre partagé
    admin_client.app.state.harpocrate_vaults_service.get_by_id = AsyncMock(  # type: ignore[attr-defined]
        return_value=vault
    )
    return str(vault.id)


class _FakeEmbedder:
    async def embed_query(self, text: str) -> list[float]:
        return [0.0] * 1024


class _FailingEmbedder:
    async def embed_query(self, text: str) -> list[float]:
        raise RuntimeError(
            "service d'embedding http://ollama:11434/api/embed (modèle 'x') : HTTP 404"
        )


class _FakeReranker:
    async def rerank(self, *, query: str, documents: list[str], top_k: int):
        return [(0, 0.9), (1, 0.1)]


async def _fake_call_llm(**kwargs):
    return {"answer": "pong", "usage": {}}


def test_endpoint_test_ok_vectorization_and_rerank(
    admin_client: TestClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    vault_id = _allow_vault(admin_client)
    import rag.services.endpoint_test as et

    monkeypatch.setattr(et, "make_provider", lambda **kw: _FakeEmbedder())
    monkeypatch.setattr(et, "make_rerank_provider", lambda **kw: _FakeReranker())
    monkeypatch.setattr(et, "call_llm", _fake_call_llm)

    r = admin_client.post(
        f"/api/admin/harpocrate-vaults/{vault_id}/endpoints/test",
        headers=admin_headers,
        json={
            "indexer": {"provider": "openai", "model": "text-embedding-3-small"},
            "rerank": {"provider": "ollama", "model": "bge-reranker-v2-m3",
                       "base_url": "http://x:11434"},
            "llm": {"provider": "ollama", "model": "qwen3:14b",
                    "base_url": "http://x:11434"},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["vectorization"]["ok"] is True
    assert "1024" in body["vectorization"]["message"]
    assert body["rerank"]["ok"] is True
    assert body["llm"]["ok"] is True
    assert "pong" in body["llm"]["message"]


def test_endpoint_test_unknown_model_fails_without_calling_provider(
    admin_client: TestClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    vault_id = _allow_vault(admin_client)
    import rag.services.endpoint_test as et

    called = MagicMock()
    monkeypatch.setattr(et, "make_provider", called)

    r = admin_client.post(
        f"/api/admin/harpocrate-vaults/{vault_id}/endpoints/test",
        headers=admin_headers,
        json={"indexer": {"provider": "ollama", "model": "modele-fantome"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["vectorization"]["ok"] is False
    assert "registre" in body["vectorization"]["message"]
    assert body["rerank"] is None
    assert body["llm"] is None
    called.assert_not_called()


def test_endpoint_test_provider_error_is_reported_with_context(
    admin_client: TestClient, admin_headers: dict[str, str], monkeypatch
) -> None:
    vault_id = _allow_vault(admin_client)
    import rag.services.endpoint_test as et

    monkeypatch.setattr(et, "make_provider", lambda **kw: _FailingEmbedder())

    r = admin_client.post(
        f"/api/admin/harpocrate-vaults/{vault_id}/endpoints/test",
        headers=admin_headers,
        json={"indexer": {"provider": "openai", "model": "text-embedding-3-small"}},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["vectorization"]["ok"] is False
    assert "HTTP 404" in body["vectorization"]["message"]
