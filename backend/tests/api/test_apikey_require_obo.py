"""Clé « OBO obligatoire » : refus 401 `obo_required` sur toutes les surfaces
clé API sans identité humaine signée et connue ; passage avec (epic f3cc98a8)."""

from __future__ import annotations

import asyncio
import time

import asyncpg
from fastapi.testclient import TestClient

from rag.auth.obo import sign_actor
from tests.api._helpers import make_ws_with_user_key

_GUID = "5b0c6a7e-1f2d-4c3b-9a8e-0d1e2f3a4b5c"
_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
_LIST_WORKSPACES = {
    "jsonrpc": "2.0",
    "id": 1,
    "method": "tools/call",
    "params": {"name": "list_workspaces", "arguments": {}},
}


def _obo_key(client: TestClient, admin_headers: dict[str, str], ws: str) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, ws)
    keys = client.get("/api/me/api-keys", headers=admin_headers).json()
    key_id = next(k["id"] for k in keys if k["name"] == f"key-{ws}")
    resp = client.patch(
        f"/api/me/api-keys/{key_id}",
        headers=admin_headers,
        json={"require_obo": True},
    )
    assert resp.status_code == 204
    return api_key


def _seed_user_identity(dsn: str) -> None:
    async def seed() -> None:
        conn = await asyncpg.connect(dsn)
        try:
            await conn.execute("DELETE FROM users WHERE email = 'dora@example.com'")
            await conn.execute(
                "INSERT INTO users (username, email, password_hash, identity) "
                "VALUES ('dora', 'dora@example.com', '', $1)",
                _GUID,
            )
        finally:
            await conn.close()

    asyncio.run(seed())


def _signed(api_key: str, actor: str = _GUID) -> dict[str, str]:
    ts = int(time.time())
    return {
        "x-portal-actor": actor,
        "x-portal-actor-timestamp": str(ts),
        "x-portal-actor-signature": sign_actor(actor, ts, api_key),
    }


def test_index_with_require_obo_key_without_identity_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _obo_key(admin_client, admin_headers, "ws_obo_rest")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"workspace": "ws_obo_rest", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "obo_required"


def test_index_with_require_obo_key_and_unknown_identity_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _obo_key(admin_client, admin_headers, "ws_obo_unknown")
    r = admin_client.post(
        "/api/v1/index",
        headers={
            "Authorization": f"Bearer {api_key}",
            **_signed(api_key, actor="00000000-0000-4000-8000-0000000000ff"),
        },
        json={"workspace": "ws_obo_unknown", "path": "x.md", "content": "y"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "obo_required"


def test_mcp_with_require_obo_key_without_identity_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _obo_key(admin_client, admin_headers, "ws_obo_mcp")
    r = admin_client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {api_key}", **_MCP_HEADERS},
        json=_LIST_WORKSPACES,
    )
    assert r.status_code == 401
    assert r.json() == {"error": "obo_required"}


def test_mcp_with_require_obo_key_and_signed_identity_passes(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    pg_container: str,
    cleanup_ws_dbs_api: None,
) -> None:
    api_key = _obo_key(admin_client, admin_headers, "ws_obo_mcp_ok")
    _seed_user_identity(pg_container)
    r = admin_client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {api_key}", **_MCP_HEADERS, **_signed(api_key)},
        json=_LIST_WORKSPACES,
    )
    assert r.status_code == 200, r.text


def test_search_with_require_obo_key_in_body_without_identity_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _obo_key(admin_client, admin_headers, "ws_obo_search")
    r = admin_client.post(
        "/api/v1/search",
        json={"workspace": "ws_obo_search", "api_key": api_key, "query": "q"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "obo_required"
