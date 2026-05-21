"""Tests E2E des endpoints `/workspaces/{name}/chunking-config` (M9-T8).

Cf. spec `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`
§5 et plan task 8. Couvre les 6 codes de retour listés au §5.2 :

- 200 GET (config par défaut hydratée à la création du workspace via T6).
- 404 GET workspace inconnu.
- 204 PUT payload identique.
- 200 PUT changement sans documents indexés.
- 409 PUT changement avec documents + ``confirm=false``.
- 202 PUT changement avec documents + ``confirm=true``.
- 422 PUT payload Pydantic invalide.
- 404 PUT workspace inconnu.
"""

from __future__ import annotations

import asyncio
import os

import asyncpg
from fastapi.testclient import TestClient


def _create_ws(client: TestClient, headers: dict[str, str], name: str) -> str:
    """Crée un workspace via POST /workspaces. Retourne son id."""
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={
            "name": name,
            "api_key_vault": "rag",
            "indexer": {
                "provider": "ollama",
                "model": "mxbai-embed-large",
                "api_key_ref": None,
                "base_url": "http://stub:11434",
            },
        },
    )
    assert r.status_code == 201, r.text
    return str(r.json()["id"])


def _insert_doc(workspace_name: str) -> None:
    """Insère un document indexé minimal pour le workspace donné.

    Pattern aligné sur ``test_admin_reindex_jobs.py::_setup_ws_with_doc``.
    """

    async def _go() -> None:
        conn = await asyncpg.connect(os.environ["DATABASE_URL"])
        try:
            ws_id = await conn.fetchval("SELECT id FROM workspaces WHERE name=$1", workspace_name)
            await conn.execute(
                "INSERT INTO indexed_documents "
                "(workspace_id, path, content_hash, indexer_used) "
                "VALUES ($1, 'x.md', 'sha256:0', 'ollama/mxbai-embed-large')",
                ws_id,
            )
        finally:
            await conn.close()

    asyncio.get_event_loop().run_until_complete(_go())


def test_get_chunking_config_returns_default(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_get"
    _create_ws(admin_client, admin_headers, name)
    r = admin_client.get(f"/api/admin/workspaces/{name}/chunking-config", headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["strategy"] == "paragraph"
    assert body["max_chars"] == 2000
    assert body["min_chars"] == 200
    assert body["overlap_chars"] == 200
    assert body["extras"] == {}


def test_get_chunking_config_404_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/api/admin/workspaces/nope/chunking-config", headers=admin_headers)
    assert r.status_code == 404


def test_put_chunking_config_identical_returns_204(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_id"
    _create_ws(admin_client, admin_headers, name)
    r = admin_client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 2000,
            "min_chars": 200,
            "overlap_chars": 200,
            "extras": {},
        },
    )
    assert r.status_code == 204


def test_put_chunking_config_no_docs_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_chg"
    _create_ws(admin_client, admin_headers, name)
    r = admin_client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 1500,
            "min_chars": 100,
            "overlap_chars": 150,
            "extras": {},
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["max_chars"] == 1500
    assert body["min_chars"] == 100
    assert body["overlap_chars"] == 150


def test_put_chunking_config_with_docs_no_confirm_returns_409(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_409"
    _create_ws(admin_client, admin_headers, name)
    _insert_doc(name)
    r = admin_client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 1500,
            "min_chars": 100,
            "overlap_chars": 150,
            "extras": {},
        },
    )
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["error"] == "chunking_change_requires_reindex"
    assert body["workspace"] == name
    assert body["action"] == f"PUT /workspaces/{name}/chunking-config?confirm=true"


def test_put_chunking_config_with_docs_and_confirm_returns_202(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_202"
    _create_ws(admin_client, admin_headers, name)
    _insert_doc(name)
    r = admin_client.put(
        f"/api/admin/workspaces/{name}/chunking-config?confirm=true",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 1500,
            "min_chars": 100,
            "overlap_chars": 150,
            "extras": {},
        },
    )
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["triggered_by"] == "reindex_chunking_change"
    assert body["status"] == "pending"


def test_put_chunking_config_invalid_payload_returns_422(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    name = "ws_chunk_422"
    _create_ws(admin_client, admin_headers, name)
    r = admin_client.put(
        f"/api/admin/workspaces/{name}/chunking-config",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 100,
            "min_chars": 200,
            "overlap_chars": 50,
            "extras": {},
        },
    )
    assert r.status_code == 422


def test_put_chunking_config_404_unknown_workspace(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.put(
        "/api/admin/workspaces/nope/chunking-config",
        headers=admin_headers,
        json={
            "strategy": "paragraph",
            "max_chars": 2000,
            "min_chars": 200,
            "overlap_chars": 200,
            "extras": {},
        },
    )
    assert r.status_code == 404
