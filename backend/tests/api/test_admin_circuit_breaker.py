from __future__ import annotations

import asyncio
import os

import asyncpg
from fastapi.testclient import TestClient

from rag.services.circuit_breaker import open_circuit


def _create_workspace(
    client: TestClient, headers: dict[str, str], name: str
) -> None:
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text


async def _seed_open_circuit(ws_name: str, error_msg: str = "test error") -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        ws_id = await conn.fetchval(
            "SELECT id FROM workspaces WHERE name=$1", ws_name
        )
        assert ws_id is not None, f"workspace {ws_name!r} not found"
        pool_mock = _PoolMock(conn)
        await open_circuit(
            pool_mock,  # type: ignore[arg-type]
            workspace_id=ws_id,
            provider="openai",
            model="text-embedding-3-small",
            error_message=error_msg,
        )
    finally:
        await conn.close()


class _PoolMock:
    """Adapte asyncpg.Connection pour satisfaire l'interface asyncpg.Pool
    utilisée par open_circuit (uniquement pool.execute)."""

    def __init__(self, conn: asyncpg.Connection) -> None:
        self._conn = conn

    async def execute(self, query: str, *args: object) -> str:
        return await self._conn.execute(query, *args)  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# GET /api/admin/workspaces/{name}/circuit-breaker
# ---------------------------------------------------------------------------

def test_get_circuit_breaker_401_no_auth(admin_client: TestClient) -> None:
    r = admin_client.get("/api/admin/workspaces/ws/circuit-breaker")
    assert r.status_code == 401


def test_get_circuit_breaker_404_workspace_not_found(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get(
        "/api/admin/workspaces/nonexistent_cb_ws/circuit-breaker",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_get_circuit_breaker_200_closed(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_cb_api_get_closed")
    r = admin_client.get(
        "/api/admin/workspaces/ws_cb_api_get_closed/circuit-breaker",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json() == {"status": "closed"}


def test_get_circuit_breaker_200_open(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_cb_api_get_open")
    asyncio.get_event_loop().run_until_complete(
        _seed_open_circuit("ws_cb_api_get_open", "quota exhausted")
    )

    r = admin_client.get(
        "/api/admin/workspaces/ws_cb_api_get_open/circuit-breaker",
        headers=admin_headers,
    )
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "open"
    assert body["provider"] == "openai"
    assert body["model"] == "text-embedding-3-small"
    assert body["error_message"] == "quota exhausted"
    assert "opened_at" in body
    assert "open_until" in body


# ---------------------------------------------------------------------------
# POST /api/admin/workspaces/{name}/circuit-breaker/close
# ---------------------------------------------------------------------------

def test_close_circuit_breaker_401_no_auth(admin_client: TestClient) -> None:
    r = admin_client.post("/api/admin/workspaces/ws/circuit-breaker/close")
    assert r.status_code == 401


def test_close_circuit_breaker_404_workspace_not_found(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/api/admin/workspaces/nonexistent_cb_ws/circuit-breaker/close",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_close_circuit_breaker_404_no_open_circuit(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_cb_api_close_none")
    r = admin_client.post(
        "/api/admin/workspaces/ws_cb_api_close_none/circuit-breaker/close",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "no_open_circuit"


def test_close_circuit_breaker_204(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    _create_workspace(admin_client, admin_headers, "ws_cb_api_close_ok")
    asyncio.get_event_loop().run_until_complete(
        _seed_open_circuit("ws_cb_api_close_ok")
    )

    r = admin_client.post(
        "/api/admin/workspaces/ws_cb_api_close_ok/circuit-breaker/close",
        headers=admin_headers,
    )
    assert r.status_code == 204

    # Vérification : GET retourne closed
    r2 = admin_client.get(
        "/api/admin/workspaces/ws_cb_api_close_ok/circuit-breaker",
        headers=admin_headers,
    )
    assert r2.json()["status"] == "closed"


def test_close_circuit_breaker_idempotent_returns_404(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Deuxieme fermeture retourne 404 (pas idempotent)."""
    _create_workspace(admin_client, admin_headers, "ws_cb_api_close_idem")
    asyncio.get_event_loop().run_until_complete(
        _seed_open_circuit("ws_cb_api_close_idem")
    )

    r1 = admin_client.post(
        "/api/admin/workspaces/ws_cb_api_close_idem/circuit-breaker/close",
        headers=admin_headers,
    )
    assert r1.status_code == 204

    r2 = admin_client.post(
        "/api/admin/workspaces/ws_cb_api_close_idem/circuit-breaker/close",
        headers=admin_headers,
    )
    assert r2.status_code == 404
    assert r2.json()["detail"] == "no_open_circuit"
