from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


def _make_ws(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    r = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={
            "name": name,
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201
    return r.json()["api_key"]


class _FakeProvider:
    async def embed_texts(self, texts):  # type: ignore[no-untyped-def]
        return [[0.1] * 1536 for _ in texts]

    async def embed_query(self, _t):  # type: ignore[no-untyped-def]
        return [0.1] * 1536


@pytest.fixture(autouse=True)
def _restore_make_provider():  # type: ignore[no-untyped-def]
    import rag.services.mcp as _mod
    from rag.indexer.providers.factory import make_provider as _real

    yield
    _mod.make_provider = _real  # type: ignore[assignment]


def _inject_fake_provider() -> None:
    import rag.services.mcp as _mcp_mod

    _mcp_mod.make_provider = lambda **_kw: _FakeProvider()  # type: ignore[assignment]


def test_mcp_422_for_empty_body(admin_client: TestClient, cleanup_ws_dbs_api: None) -> None:
    r = admin_client.post("/mcp", json={})
    assert r.status_code == 422


def test_mcp_422_for_missing_query(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_err_q")
    r = admin_client.post(
        "/mcp",
        json={"workspace": "ws_err_q", "api_key": "x"},
    )
    assert r.status_code == 422


def test_mcp_422_for_mix_workspace_and_workspaces(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_a",
            "api_key": "k",
            "workspaces": [{"name": "ws_b", "api_key": "k2"}],
            "query": "x",
        },
    )
    assert r.status_code == 422


def test_mcp_422_for_top_k_above_50(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_err_topk")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_topk",
            "api_key": api_key,
            "query": "x",
            "top_k": 51,
        },
    )
    assert r.status_code == 422


def test_mcp_422_for_min_score_above_one(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _make_ws(admin_client, admin_headers, "ws_err_minscore")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_minscore",
            "api_key": api_key,
            "query": "x",
            "min_score": 1.5,
        },
    )
    assert r.status_code == 422


def test_mcp_404_for_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={"workspace": "ghost", "api_key": "x", "query": "y"},
    )
    assert r.status_code == 404
    assert r.json()["error"] == "workspace_not_found"


def test_mcp_401_for_bad_api_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "ws_err_badkey")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspace": "ws_err_badkey",
            "api_key": "not-the-real-one",
            "query": "y",
        },
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_mcp_multi_fail_fast_one_bad_apikey(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key_a = _make_ws(admin_client, admin_headers, "ws_ff_a")
    _make_ws(admin_client, admin_headers, "ws_ff_b")
    _inject_fake_provider()
    r = admin_client.post(
        "/mcp",
        json={
            "workspaces": [
                {"name": "ws_ff_a", "api_key": key_a},
                {"name": "ws_ff_b", "api_key": "wrong-key"},
            ],
            "query": "x",
        },
    )
    # Une tâche lève 401 → propage via asyncio.gather fail-fast.
    assert r.status_code == 401
