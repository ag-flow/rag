"""Isolation par propriétaire des sous-ressources workspace (migration 068).

Les endpoints admin sous ``/api/admin/workspaces/{name}/*`` doivent appliquer
la même visibilité owner que la liste/détail : un workspace d'AUTRUI (owner_id
non NULL, différent du caller) doit paraître inexistant (404), tandis qu'un
workspace PARTAGÉ (owner NULL) reste accessible à tous.

Le client admin s'authentifie par master key → owner « système ». On seed
directement un workspace possédé par un autre owner (OWNER_A) : le caller
master key ne doit pas y accéder. Un workspace partagé doit rester accessible.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
from fastapi.testclient import TestClient

OWNER_A = "a" * 64


async def _seed_workspace(name: str, owner_id: str | None) -> None:
    conn = await asyncpg.connect(os.environ["DATABASE_URL"])
    try:
        await conn.execute(
            """
            INSERT INTO workspaces (name, rag_cnx, rag_base, owner_id)
            VALUES ($1, $2, $3, $4)
            """,
            name,
            "postgresql://test/c",
            f"rag_{name}",
            owner_id,
        )
    finally:
        await conn.close()


# ── Workspace d'autrui : sous-ressources introuvables (404) ──────────────────


def test_foreign_workspace_sources_hidden(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    asyncio.run(_seed_workspace("ws_owned_by_a_sources", OWNER_A))
    r = admin_client.get(
        "/api/admin/workspaces/ws_owned_by_a_sources/sources",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_foreign_workspace_hybrid_config_hidden(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    asyncio.run(_seed_workspace("ws_owned_by_a_hybrid", OWNER_A))
    r = admin_client.put(
        "/api/admin/workspaces/ws_owned_by_a_hybrid/hybrid-config",
        headers=admin_headers,
        json={
            "enabled": True,
            "rrf_k": 60,
            "weight_lexical": 0.5,
            "weight_vector": 0.5,
            "lexical_engine": "fts",
        },
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


def test_foreign_workspace_circuit_breaker_hidden(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    asyncio.run(_seed_workspace("ws_owned_by_a_cb", OWNER_A))
    r = admin_client.get(
        "/api/admin/workspaces/ws_owned_by_a_cb/circuit-breaker",
        headers=admin_headers,
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "workspace_not_found"


# ── Workspace partagé (owner NULL) : la garde n'entrave pas l'accès ──────────


def test_shared_workspace_sources_accessible(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    asyncio.run(_seed_workspace("ws_shared_sources", None))
    r = admin_client.get(
        "/api/admin/workspaces/ws_shared_sources/sources",
        headers=admin_headers,
    )
    assert r.status_code == 200
    assert r.json() == []
