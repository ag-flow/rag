"""Partage des endpoints sur les surfaces réelles (migration 095, epic f3cc98a8).

Acteurs : Alice possède un coffre privé et son endpoint ; Bob est un tiers.
Le client admin des tests s'authentifie par master key, donc comme l'owner
système — un troisième acteur, propriétaire de son propre coffre pour éprouver
les routes de gestion du partage.
"""

from __future__ import annotations

import asyncio
import json
import time
from hashlib import sha256
from typing import Any

import asyncpg
import pytest
from fastapi.testclient import TestClient

from rag.auth.obo import sign_actor
from rag.auth.owner import principal_to_owner_id
from rag.services.harpocrate_vaults import HarpocrateVaultsService

_ALICE = "alice@example.com"
_BOB = "bob@example.com"
_SYSTEM_OWNER = principal_to_owner_id("system@rag.local")
_BOB_GUID = "8e1f7c2a-3b4d-4e5f-9a6b-7c8d9e0f1a2b"
_MCP_HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


@pytest.fixture(autouse=True)
def _real_vault_lookup(admin_client: TestClient) -> None:
    """Le stub de coffres du conftest ne lit pas `harpocrate_vaults` ; les routes
    de partage décident sur le propriétaire RÉEL du coffre — on branche donc la
    lecture réelle (pure requête SQL, aucun appel Harpocrate)."""

    async def get_by_id(conn: asyncpg.Connection, vault_id: Any) -> Any:
        return await HarpocrateVaultsService.get_by_id(None, conn, vault_id)  # type: ignore[arg-type]

    admin_client.app.state.harpocrate_vaults_service.get_by_id = get_by_id  # type: ignore[attr-defined]


def _run(dsn: str, *statements: tuple[str, tuple[Any, ...]]) -> list[Any]:
    async def go() -> list[Any]:
        conn = await asyncpg.connect(dsn)
        try:
            return [await conn.fetchval(sql, *args) for sql, args in statements]
        finally:
            await conn.close()

    return asyncio.run(go())


def _seed_world(dsn: str) -> dict[str, Any]:
    """Coffre privé d'Alice + endpoint, coffre de l'owner système + endpoint, Bob."""
    vault_sql = (
        "INSERT INTO harpocrate_vaults "
        "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default, owner_id) "
        "VALUES (gen_random_uuid(), $1, $1, 'https://harpo', 'k', "
        "pgp_sym_encrypt('s', 'passphrase-of-at-least-32-characters-long'), false, $2) "
        "RETURNING id"
    )
    alice_vault, system_vault = _run(
        dsn,
        (vault_sql, ("alice-vault", principal_to_owner_id(_ALICE))),
        (vault_sql, ("system-vault", _SYSTEM_OWNER)),
    )
    ep_sql = (
        "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model, "
        "indexer_api_key_ref) VALUES ($1, $2, $2, 'openai', 'text-embedding-3-small', "
        "'openai_embedding_key') RETURNING id"
    )
    user_sql = (
        "INSERT INTO users (username, email, password_hash, identity) "
        "VALUES ($1, $1, '', $2) RETURNING id"
    )
    alice_ep, system_ep, bob_id = _run(
        dsn,
        (ep_sql, (alice_vault, "alice-ep")),
        (ep_sql, (system_vault, "system-ep")),
        (user_sql, (_BOB, _BOB_GUID)),
    )
    return {
        "alice_vault": str(alice_vault),
        "alice_ep": str(alice_ep),
        "system_vault": str(system_vault),
        "system_ep": str(system_ep),
        "bob_id": str(bob_id),
    }


def _key(dsn: str, owner_email: str, value: str) -> str:
    """Clé API `admin` d'un owner donné, insérée par son empreinte (show-once)."""
    _run(
        dsn,
        (
            "INSERT INTO user_api_keys (owner_id, name, fingerprint, scope) "
            "VALUES ($1, $2, $3, 'admin') RETURNING id",
            (principal_to_owner_id(owner_email), f"k-{value}", sha256(value.encode()).hexdigest()),
        ),
    )
    return value


def _share_with_bob(dsn: str, world: dict[str, Any]) -> None:
    _run(
        dsn,
        (
            "INSERT INTO vault_endpoint_shares (endpoint_id, user_id, owner_id) "
            "VALUES ($1::uuid, $2::uuid, $3) RETURNING endpoint_id",
            (world["alice_ep"], world["bob_id"], principal_to_owner_id(_BOB)),
        ),
    )


def _create_by_key(client: TestClient, key: str, name: str, **headers: str):  # type: ignore[no-untyped-def]
    return client.post(
        "/api/v1/workspaces",
        headers={"Authorization": f"Bearer {key}", **headers},
        json={"name": name, "vault": "alice-vault", "endpoint": "alice-ep"},
    )


def _mcp(client: TestClient, key: str, tool: str, arguments: dict[str, Any]) -> str:
    r = client.post(
        "/mcp",
        headers={"Authorization": f"Bearer {key}", **_MCP_HEADERS},
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": tool, "arguments": arguments},
        },
    )
    assert r.status_code == 200, r.text
    body = r.text
    if body.startswith("event:") or "data:" in body:
        body = next(line[5:].strip() for line in body.splitlines() if line.startswith("data:"))
    return str(json.loads(body)["result"]["content"][0]["text"])


def test_admin_create_with_unshared_endpoint_of_another_vault_returns_404(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    pg_container: str,
    cleanup_ws_dbs_api: None,
) -> None:
    """Régression : l'id seul donnait l'endpoint (et les clés) du coffre d'autrui."""
    world = _seed_world(pg_container)
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": "steal", "label": "steal", "endpoint_id": world["alice_ep"]},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "endpoint_not_found"


def test_rest_create_by_third_party_refused_then_accepted_once_shared(
    admin_client: TestClient, pg_container: str, cleanup_ws_dbs_api: None
) -> None:
    world = _seed_world(pg_container)
    bob_key = _key(pg_container, _BOB, "bob-key-rest")

    refused = _create_by_key(admin_client, bob_key, "bob-ws-rest")
    assert refused.status_code == 404
    assert refused.json()["error"] == "vault_not_found"

    _share_with_bob(pg_container, world)
    accepted = _create_by_key(admin_client, bob_key, "bob-ws-rest")
    assert accepted.status_code == 201, accepted.text


def test_rest_create_accepted_when_shared_with_the_obo_identity(
    admin_client: TestClient, pg_container: str, cleanup_ws_dbs_api: None
) -> None:
    """La clé appartient à un tiers (Alice n'a rien partagé à son porteur), mais
    l'humain signé est Bob, bénéficiaire du partage : on accepte."""
    world = _seed_world(pg_container)
    _share_with_bob(pg_container, world)
    portal_key = _key(pg_container, "portal@example.com", "portal-key")
    ts = int(time.time())
    obo = {
        "x-portal-actor": _BOB_GUID,
        "x-portal-actor-timestamp": str(ts),
        "x-portal-actor-signature": sign_actor(_BOB_GUID, ts, portal_key),
    }

    assert _create_by_key(admin_client, portal_key, "obo-ws-noid").status_code == 404
    assert _create_by_key(admin_client, portal_key, "obo-ws", **obo).status_code == 201


def test_mcp_lists_shared_endpoint_and_reset_refused_after_unshare(
    admin_client: TestClient, pg_container: str, cleanup_ws_dbs_api: None
) -> None:
    world = _seed_world(pg_container)
    bob_key = _key(pg_container, _BOB, "bob-key-mcp")
    assert "alice-vault" not in _mcp(admin_client, bob_key, "list_endpoints", {})

    _share_with_bob(pg_container, world)
    listed = json.loads(_mcp(admin_client, bob_key, "list_endpoints", {}))
    shared = next(g for g in listed if g["vault"] == "alice-vault")
    assert shared["writable"] is False
    assert shared["shared"] is True
    assert [e["slug"] for e in shared["endpoints"]] == ["alice-ep"]

    created = _mcp(
        admin_client,
        bob_key,
        "create_workspace",
        {"name": "bob-ws-mcp", "vault": "alice-vault", "endpoint": "alice-ep"},
    )
    assert json.loads(created)["name"] == "bob-ws-mcp"

    _run(pg_container, ("DELETE FROM vault_endpoint_shares RETURNING 1", ()))
    reset = _mcp(
        admin_client, bob_key, "reset_workspace_from_endpoint", {"workspace": "bob-ws-mcp"}
    )
    assert "n'est plus partagé" in reset
    # Snapshot : le workspace créé reste en place après le retrait du partage.
    assert "bob-ws-mcp" in _mcp(admin_client, bob_key, "list_workspaces", {})


def test_sharing_routes_owner_can_replace_state(
    admin_client: TestClient, admin_headers: dict[str, str], pg_container: str
) -> None:
    world = _seed_world(pg_container)
    url = (
        f"/api/admin/harpocrate-vaults/{world['system_vault']}"
        f"/endpoints/{world['system_ep']}/sharing"
    )

    put = admin_client.put(
        url, headers=admin_headers, json={"shared_with_all": False, "user_ids": [world["bob_id"]]}
    )
    assert put.status_code == 200, put.text
    assert [u["email"] for u in put.json()["users"]] == [_BOB]
    assert admin_client.get(url, headers=admin_headers).json() == put.json()

    bad = admin_client.put(
        url,
        headers=admin_headers,
        json={"shared_with_all": False, "user_ids": ["00000000-0000-4000-8000-000000000000"]},
    )
    assert bad.status_code == 422
    assert bad.json()["detail"] == "unknown_user"


def test_sharing_routes_refuse_non_owner_and_foreign_endpoint(
    admin_client: TestClient, admin_headers: dict[str, str], pg_container: str
) -> None:
    world = _seed_world(pg_container)
    alice_url = (
        f"/api/admin/harpocrate-vaults/{world['alice_vault']}/endpoints/{world['alice_ep']}/sharing"
    )
    assert admin_client.get(alice_url, headers=admin_headers).status_code == 403
    assert (
        admin_client.put(
            alice_url, headers=admin_headers, json={"shared_with_all": True}
        ).status_code
        == 403
    )
    # Endpoint d'Alice désigné sous le coffre de l'owner système : 404, pas 200.
    mixed = (
        f"/api/admin/harpocrate-vaults/{world['system_vault']}"
        f"/endpoints/{world['alice_ep']}/sharing"
    )
    assert admin_client.get(mixed, headers=admin_headers).status_code == 404


def test_usable_endpoints_and_share_candidates(
    admin_client: TestClient, admin_headers: dict[str, str], pg_container: str
) -> None:
    world = _seed_world(pg_container)
    usable = admin_client.get("/api/admin/endpoints/usable", headers=admin_headers).json()
    by_id = {e["id"]: e for e in usable}
    assert by_id[world["system_ep"]]["access"] == "owned"
    assert world["alice_ep"] not in by_id
    # Aucune référence de secret dans ce que voit un utilisateur de l'endpoint.
    assert "api_key_ref" not in json.dumps(usable)

    _run(
        pg_container,
        (
            "UPDATE vault_endpoints SET shared_with_all = true WHERE slug = 'alice-ep' RETURNING 1",
            (),
        ),
    )
    usable = admin_client.get("/api/admin/endpoints/usable", headers=admin_headers).json()
    assert {e["id"]: e for e in usable}[world["alice_ep"]]["access"] == "shared"

    bob = admin_client.get(
        "/api/admin/endpoint-share-candidates",
        headers=admin_headers,
        params={"email": "Bob@Example.com"},
    )
    assert bob.status_code == 200
    assert bob.json()["id"] == world["bob_id"]
    unknown = admin_client.get(
        "/api/admin/endpoint-share-candidates",
        headers=admin_headers,
        params={"email": "nobody@example.com"},
    )
    assert unknown.status_code == 404
    # Sans email exact, aucune liste d'utilisateurs n'est renvoyée.
    listing = admin_client.get("/api/admin/endpoint-share-candidates", headers=admin_headers)
    assert listing.status_code == 422


def test_share_candidate_lookup_refuses_the_caller_himself(
    admin_client: TestClient, admin_headers: dict[str, str], pg_container: str
) -> None:
    """Le client de test s'authentifie comme l'owner système (system@rag.local)."""
    _run(
        pg_container,
        (
            "INSERT INTO users (username, email, password_hash) "
            "VALUES ('system', 'system@rag.local', '') RETURNING id",
            (),
        ),
    )
    r = admin_client.get(
        "/api/admin/endpoint-share-candidates",
        headers=admin_headers,
        params={"email": "system@rag.local"},
    )
    assert r.status_code == 422
    assert r.json()["detail"] == "cannot_share_with_self"
