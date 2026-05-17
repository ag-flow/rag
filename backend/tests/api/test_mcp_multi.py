from __future__ import annotations

import asyncio

import asyncpg
import pytest
from fastapi.testclient import TestClient
from pgvector.asyncpg import register_vector


def _run_async(coro):  # type: ignore[no-untyped-def]
    """Fresh event loop pour les sync tests appelant du code async,
    isolé du Runner pytest-asyncio session-scoped (cf. T10 lesson)."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


def _make_ws(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    provider: str = "openai",
    model: str = "text-embedding-3-small",
    api_key_ref: str | None = "openai_embedding_key",
    base_url: str | None = None,
) -> str:
    indexer_body: dict[str, object] = {"provider": provider, "model": model}
    if api_key_ref is not None:
        indexer_body["api_key_ref"] = api_key_ref
    if base_url is not None:
        indexer_body["base_url"] = base_url
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": name, "indexer": indexer_body},
    )
    assert r.status_code == 201, r.text
    return r.json()["api_key"]


class _FakeProvider:
    def __init__(self, vec: list[float]) -> None:
        self._vec = vec

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [self._vec for _ in texts]

    async def embed_query(self, _text: str) -> list[float]:
        return self._vec


@pytest.fixture(autouse=True)
def _restore_make_provider():  # type: ignore[no-untyped-def]
    """Restore le vrai make_provider après chaque test."""
    import rag.services.mcp as _mod
    from rag.indexer.providers.factory import make_provider as _real

    yield
    _mod.make_provider = _real  # type: ignore[assignment]


async def _seed(pg_container: str, ws: str, path: str, content: str, vec: list[float]) -> None:
    """Insert un row dans rag_<ws>.embeddings."""
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/rag_{ws}"
    conn = await asyncpg.connect(ws_dsn)
    try:
        await register_vector(conn)
        await conn.execute(
            "INSERT INTO embeddings (path, chunk_index, content, embedding) VALUES ($1, 0, $2, $3)",
            path,
            content,
            vec,
        )
    finally:
        await conn.close()


def test_mcp_multi_returns_hits_from_all_workspaces_in_order(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_m_a")
    key_b = _make_ws(admin_client, admin_headers, "ws_m_b")

    dim = 1536
    near = [1.0] + [0.0] * (dim - 1)

    async def _go() -> None:
        await _seed(pg_container, "ws_m_a", "a_doc.md", "from a", near)
        await _seed(pg_container, "ws_m_b", "b_doc.md", "from b", near)

    _run_async(_go())

    fake = _FakeProvider(vec=near)
    import rag.services.mcp as _mcp_mod

    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_m_a", "api_key": key_a},
                {"name": "ws_m_b", "api_key": key_b},
            ],
            "query": "x",
            "top_k": 5,
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    paths = [h["path"] for h in body["results"]]
    assert paths == ["a_doc.md", "b_doc.md"]


def test_mcp_multi_each_item_carries_correct_workspace_and_indexer(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_label_a")
    key_b = _make_ws(
        admin_client,
        admin_headers,
        "ws_label_b",
        provider="voyage",
        model="voyage-3",
        api_key_ref="voyage_api_key",
    )

    # voyage-3 dimension = 1024 (depuis model_dimensions M2, migration 005)
    dim_oa = 1536
    dim_vy = 1024
    vec_oa = [1.0] + [0.0] * (dim_oa - 1)
    vec_vy = [1.0] + [0.0] * (dim_vy - 1)

    async def _go() -> None:
        await _seed(pg_container, "ws_label_a", "a.md", "x", vec_oa)
        await _seed(pg_container, "ws_label_b", "b.md", "x", vec_vy)

    _run_async(_go())

    # Fake provider sensible à la dimension du modèle.
    class _DimAwareFake:
        async def embed_texts(self, _t):  # type: ignore[no-untyped-def]
            raise AssertionError("not expected in search path")

        async def embed_query(self, _t):  # type: ignore[no-untyped-def]
            return [1.0] + [0.0] * (self.dim - 1)  # type: ignore[attr-defined]

    def _factory(provider: str, model: str, **_kw):  # type: ignore[no-untyped-def]
        f = _DimAwareFake()
        f.dim = dim_oa if provider == "openai" else dim_vy  # type: ignore[attr-defined]
        return f

    import rag.services.mcp as _mcp_mod

    _mcp_mod.make_provider = _factory  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_label_a", "api_key": key_a},
                {"name": "ws_label_b", "api_key": key_b},
            ],
            "query": "x",
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    by_ws = {h["workspace"]: h for h in results}
    assert by_ws["ws_label_a"]["indexer"] == "openai/text-embedding-3-small"
    assert by_ws["ws_label_b"]["indexer"] == "voyage/voyage-3"


def test_mcp_multi_top_k_applies_per_workspace(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_topk_a")
    key_b = _make_ws(admin_client, admin_headers, "ws_topk_b")

    dim = 1536
    vec = [1.0] + [0.0] * (dim - 1)

    async def _go() -> None:
        for i in range(5):
            await _seed(pg_container, "ws_topk_a", f"a{i}.md", "x", vec)
            await _seed(pg_container, "ws_topk_b", f"b{i}.md", "x", vec)

    _run_async(_go())

    fake = _FakeProvider(vec=vec)
    import rag.services.mcp as _mcp_mod

    _mcp_mod.make_provider = lambda **_kw: fake  # type: ignore[assignment]

    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_topk_a", "api_key": key_a},
                {"name": "ws_topk_b", "api_key": key_b},
            ],
            "query": "x",
            "top_k": 2,
            "min_score": 0.0,
        },
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    # top_k=2 par workspace, 2 workspaces → 4 items total
    assert len(results) == 4
    paths_a = [h["path"] for h in results if h["workspace"] == "ws_topk_a"]
    paths_b = [h["path"] for h in results if h["workspace"] == "ws_topk_b"]
    assert len(paths_a) == 2
    assert len(paths_b) == 2
