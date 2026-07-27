"""Endpoint POST /api/workspaces/{name}/playground/search (SR5.2).

Recherche seule avec provenance par canal : suit la config hybride du
workspace (hybrid_search si activée, sinon vectoriel pur, canal lexical vide).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from rag.api.playground_search import router_search
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.db.workspace_search import ChannelEntry, HybridResult
from rag.schemas.mcp import SearchHit

_WS_ROW = {
    "ws_id": uuid4(),
    "rag_cnx": "dsn",
    "idx_provider": "openai",
    "idx_model": "text-embedding-3-small",
    "idx_api_key_ref": None,
    "idx_base_url": None,
    "idx_service": "openai",
}


def _hit(path: str, score: float) -> SearchHit:
    return SearchHit(
        workspace="ws",
        indexer="openai/text-embedding-3-small",
        path=path,
        chunk_index=0,
        content="contenu",
        score=score,
    )


def _client(monkeypatch: pytest.MonkeyPatch, *, hybrid_cfg: dict | None) -> TestClient:
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=_WS_ROW)
    # Garde owner (require_owned_workspace_id) : pool.acquire → conn.fetchval.
    conn = MagicMock()
    conn.fetchval = AsyncMock(return_value=_WS_ROW["ws_id"])
    acquire_cm = MagicMock()
    acquire_cm.__aenter__ = AsyncMock(return_value=conn)
    acquire_cm.__aexit__ = AsyncMock(return_value=False)
    pool.acquire = MagicMock(return_value=acquire_cm)

    app = FastAPI()
    # get_current_owner_id lit request.session (session vide → owner système).
    app.add_middleware(SessionMiddleware, secret_key="test")
    app.state.pools = MagicMock()
    app.state.pools.config_pool = pool
    app.state.pools.get_workspace_pool = AsyncMock(return_value=MagicMock())
    app.state.harpocrate_vaults_service = MagicMock()
    app.state.client_provider = MagicMock()
    app.include_router(router_search)
    app.dependency_overrides[require_master_key_or_authenticated_admin] = lambda: None

    provider = MagicMock()
    provider.embed_query = AsyncMock(return_value=[0.1, 0.2])
    monkeypatch.setattr(
        "rag.indexer.providers.factory.make_provider", lambda **_kw: provider
    )
    monkeypatch.setattr(
        "rag.services.mcp._load_hybrid_config", AsyncMock(return_value=hybrid_cfg)
    )
    return TestClient(app)


def _post(client: TestClient, query: str = "routage des régions") -> object:
    return client.post("/api/workspaces/ws/playground/search", json={"query": query})


class TestPlaygroundSearchVectorOnly:
    def test_sans_config_hybride_canal_lexical_vide(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rag.db.workspace_search.vector_search",
            AsyncMock(return_value=[_hit("a.md", 0.9), _hit("b.md", 0.8)]),
        )
        resp = _post(_client(monkeypatch, hybrid_cfg=None))

        assert resp.status_code == 200
        data = resp.json()
        assert data["hybrid_enabled"] is False
        assert data["lexical_channel"] == []
        assert [c["rank"] for c in data["vector_channel"]] == [1, 2]
        assert data["rrf_k"] == 60
        assert data["lexical_engine"] == "fts"

    def test_config_hybride_desactivee_reste_vectoriel(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "rag.db.workspace_search.vector_search",
            AsyncMock(return_value=[_hit("a.md", 0.9)]),
        )
        cfg = {
            "enabled": False,
            "rrf_k": 40,
            "weight_lexical": 0.3,
            "weight_vector": 0.7,
            "lexical_engine": "fts",
        }
        resp = _post(_client(monkeypatch, hybrid_cfg=cfg))

        assert resp.status_code == 200
        data = resp.json()
        assert data["hybrid_enabled"] is False
        assert data["rrf_k"] == 40  # la config est renvoyée telle quelle


class TestPlaygroundSearchHybrid:
    def test_hybride_renvoie_les_deux_canaux(self, monkeypatch) -> None:
        result = HybridResult(
            hits=[_hit("a.md", 0.016)],
            vector_channel=[ChannelEntry(path="a.md", chunk_index=0, rank=1, score=0.9)],
            lexical_channel=[ChannelEntry(path="b.md", chunk_index=0, rank=1, score=1.2)],
        )
        fake_hybrid = AsyncMock(return_value=result)
        monkeypatch.setattr("rag.db.workspace_search.hybrid_search", fake_hybrid)
        cfg = {
            "enabled": True,
            "rrf_k": 60,
            "weight_lexical": 0.4,
            "weight_vector": 0.6,
            "lexical_engine": "fts",
        }
        resp = _post(_client(monkeypatch, hybrid_cfg=cfg))

        assert resp.status_code == 200
        data = resp.json()
        assert data["hybrid_enabled"] is True
        assert data["weight_vector"] == pytest.approx(0.6)
        assert data["vector_channel"][0]["path"] == "a.md"
        assert data["lexical_channel"][0]["path"] == "b.md"
        assert fake_hybrid.await_args.kwargs["w_lexical"] == pytest.approx(0.4)


class TestPlaygroundSearchErrors:
    def test_404_workspace_inconnu(self, monkeypatch) -> None:
        client = _client(monkeypatch, hybrid_cfg=None)
        client.app.state.pools.config_pool.fetchrow = AsyncMock(return_value=None)

        resp = _post(client)
        assert resp.status_code == 404
