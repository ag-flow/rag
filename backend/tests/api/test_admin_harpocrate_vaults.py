from __future__ import annotations

from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient


def _payload(**overrides: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    p.update(overrides)
    return p


async def _purge_vaults(pool: asyncpg.Pool) -> None:
    async with pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")


@pytest.fixture
def app_pool(admin_client: TestClient) -> asyncpg.Pool:
    pool: asyncpg.Pool = admin_client.app.state.pools.config_pool  # type: ignore[attr-defined]
    return pool


@pytest.mark.asyncio
async def test_create_returns_201_no_api_key_in_response(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    r = admin_client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["name"] == "rag"
    # Piège : `'"api_key":'` avec le ':' final pour ne pas matcher 'api_key_id'.
    assert '"api_key":' not in r.text


@pytest.mark.asyncio
async def test_create_duplicate_name_returns_409(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    r1 = admin_client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers)
    assert r1.status_code == 201, r1.text
    r2 = admin_client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(api_key_id="k-002", is_default=False),
        headers=admin_headers,
    )
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_create_invalid_slug_returns_422(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    r = admin_client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="BAD NAME"),
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_list_no_api_key_in_response(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    admin_client.post("/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers)
    r = admin_client.get("/api/admin/harpocrate-vaults", headers=admin_headers)
    assert r.status_code == 200
    assert '"api_key":' not in r.text
    assert len(r.json()) == 1


@pytest.mark.asyncio
async def test_get_by_id(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.get(f"/api/admin/harpocrate-vaults/{created['id']}", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["id"] == created["id"]


@pytest.mark.asyncio
async def test_get_nonexistent_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get(
        "/api/admin/harpocrate-vaults/00000000-0000-0000-0000-000000000000",
        headers=admin_headers,
    )
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_patch_name_field_rejected_422(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"name": "newname"},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_is_default_field_rejected_422(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"is_default": False},
        headers=admin_headers,
    )
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_patch_updates_label(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.patch(
        f"/api/admin/harpocrate-vaults/{created['id']}",
        json={"label": "Renomme"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["label"] == "Renomme"


@pytest.mark.asyncio
async def test_delete_default_alone_returns_204(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.delete(f"/api/admin/harpocrate-vaults/{created['id']}", headers=admin_headers)
    assert r.status_code == 204


@pytest.mark.asyncio
async def test_delete_default_with_others_returns_409(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    default = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    admin_client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="second", api_key_id="k-002", is_default=False),
        headers=admin_headers,
    )
    r = admin_client.delete(f"/api/admin/harpocrate-vaults/{default['id']}", headers=admin_headers)
    assert r.status_code == 409


@pytest.mark.asyncio
async def test_set_default_swaps(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    first = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    second = admin_client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(name="second", api_key_id="k-002", is_default=False),
        headers=admin_headers,
    ).json()
    r = admin_client.post(
        f"/api/admin/harpocrate-vaults/{second['id']}/set-default",
        headers=admin_headers,
    )
    assert r.status_code == 200
    refreshed_first = admin_client.get(
        f"/api/admin/harpocrate-vaults/{first['id']}", headers=admin_headers
    ).json()
    assert refreshed_first["is_default"] is False
    assert r.json()["is_default"] is True


@pytest.mark.asyncio
async def test_rotate_api_key(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.post(
        f"/api/admin/harpocrate-vaults/{created['id']}/rotate-api-key",
        json={"api_key_id": "k-002", "api_key": "newsecretXYZ987"},
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["api_key_id"] == "k-002"
    reveal = admin_client.get(
        f"/api/admin/harpocrate-vaults/{created['id']}/api-key",
        headers=admin_headers,
    )
    assert reveal.json()["api_key"] == "newsecretXYZ987"


@pytest.mark.asyncio
async def test_reveal_api_key(
    admin_client: TestClient, app_pool: asyncpg.Pool, admin_headers: dict[str, str]
) -> None:
    await _purge_vaults(app_pool)
    created = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers
    ).json()
    r = admin_client.get(
        f"/api/admin/harpocrate-vaults/{created['id']}/api-key",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json()["api_key"] == "supersecretvalue123"


def test_anonymous_returns_401(admin_client: TestClient) -> None:
    r = admin_client.get("/api/admin/harpocrate-vaults")
    assert r.status_code == 401
