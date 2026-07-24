from __future__ import annotations

import asyncio
import os

import asyncpg
from fastapi.testclient import TestClient


def _setup_ws_and_key(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    """Crée un workspace + une clé API user de niveau écriture. Retourne la clé."""
    ws = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": name, "label": name, "endpoint_id": client.default_endpoint_id},
    )
    assert ws.status_code == 201, ws.text
    key = client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": f"push-{name}", "scope": "read_write"},
    )
    assert key.status_code == 201, key.text
    return key.json()["api_key"]


def _payload_strategy_id(job_id: str) -> str | None:
    async def _fetch() -> str | None:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            value = await conn.fetchval(
                "SELECT strategy_id FROM push_job_payloads WHERE job_id=$1::uuid", job_id
            )
            return str(value) if value is not None else None
        finally:
            await conn.close()

    return asyncio.run(_fetch())


def test_push_resolves_caller_slug_to_bound_id(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _setup_ws_and_key(admin_client, admin_headers, "pushstrat-a")
    created = admin_client.post(
        "/api/admin/chunking/strategies",
        headers=admin_headers,
        json={"label": "Docflow push", "algo": "prose"},
    )
    assert created.status_code == 201, created.text

    r = admin_client.post(
        "/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "pushstrat-a",
            "path": "doc.md",
            "content": "# Hello",
            "strategy": "docflow-push",
        },
    )
    assert r.status_code == 202, r.text
    assert _payload_strategy_id(r.json()["job_id"]) == created.json()["id"]


def test_push_falls_back_to_system_strategy_slug(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _setup_ws_and_key(admin_client, admin_headers, "pushstrat-sys")
    r = admin_client.post(
        "/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "pushstrat-sys",
            "path": "doc.md",
            "content": "# Hello",
            "strategy": "markdown-deep",
        },
    )
    assert r.status_code == 202, r.text
    assert _payload_strategy_id(r.json()["job_id"]) is not None


def test_push_unknown_slug_is_422_no_silent_fallback(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _setup_ws_and_key(admin_client, admin_headers, "pushstrat-bad")
    r = admin_client.post(
        "/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={
            "workspace": "pushstrat-bad",
            "path": "doc.md",
            "content": "# Hello",
            "strategy": "strategie-fantome",
        },
    )
    assert r.status_code == 422
    assert "strategie-fantome" in r.json()["detail"]


def test_push_without_strategy_binds_nothing(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    api_key = _setup_ws_and_key(admin_client, admin_headers, "pushstrat-none")
    r = admin_client.post(
        "/index",
        headers={"Authorization": f"Bearer {api_key}"},
        json={"workspace": "pushstrat-none", "path": "doc.md", "content": "# Hello"},
    )
    assert r.status_code == 202, r.text
    assert _payload_strategy_id(r.json()["job_id"]) is None
