from __future__ import annotations

import asyncio

import asyncpg
from fastapi.testclient import TestClient

from rag.api.ingestion_journal import rejection_reason
from tests.api._helpers import make_ws_with_user_key


def test_rejection_reason_mapping() -> None:
    assert (
        rejection_reason(401, "invalid_workspace_apikey")
        == "Workspace inconnu ou non autorisé pour cette clé"
    )
    assert rejection_reason(401, "invalid_apikey") == "Clé API invalide"
    assert rejection_reason(401, "insufficient_scope") == (
        "Niveau de la clé insuffisant (écriture requise)"
    )
    assert rejection_reason(401, "missing_bearer_token") == "En-tête Authorization manquant"
    assert rejection_reason(401, "weird") == "Non authentifié"
    assert rejection_reason(404, "workspace_not_found") == (
        "Workspace inconnu (à créer avant de pousser)"
    )
    assert rejection_reason(404, "autre") == "Ressource introuvable"
    assert "Corps invalide" in rejection_reason(422, [{"loc": ["body", "content"], "msg": "x"}])
    assert rejection_reason(413, None) == "Contenu trop volumineux"


def _key(client: TestClient, admin_headers: dict[str, str], name: str) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope="read_write")
    return api_key


def test_rejected_index_is_journaled(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key = _key(admin_client, admin_headers, "ws_journal")
    # Clé valide mais workspace inexistant → 404, aucun job, rejet journalisé.
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {key}"},
        json={"workspace": "ghost", "path": "a.md", "content": "x"},
    )
    assert r.status_code == 404

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            row = await conn.fetchrow(
                "SELECT method, workspace, doc_path, http_status, reason "
                "FROM ingestion_rejections ORDER BY received_at DESC LIMIT 1"
            )
        finally:
            await conn.close()
        assert row is not None
        assert row["method"] == "POST"
        assert row["workspace"] == "ghost"
        assert row["doc_path"] == "a.md"
        assert row["http_status"] == 404
        assert row["reason"] == "Workspace inconnu (à créer avant de pousser)"

    asyncio.run(check())

    # Le rejet apparaît dans Push activity (liste globale) en statut 'rejected'.
    jobs = admin_client.get(
        "/api/admin/jobs?workspace=ghost", headers=admin_headers
    ).json()
    assert len(jobs) >= 1
    rej = jobs[0]
    assert rej["status"] == "rejected"
    assert rej["source"] == "rest_api"
    assert rej["path"] == "a.md"
    assert rej["error_message"] == "Workspace inconnu (à créer avant de pousser)"


def test_anonymous_rejection_does_not_break_jobs_list(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Régression : un rejet SANS workspace lisible (bot anonyme, corps vide) ne
    doit pas casser la liste Push activity (workspace_name NULL → 500 Pydantic)."""
    r = admin_client.post("/api/v1/index")  # ni auth ni corps → 401 journalisé
    assert r.status_code == 401

    jobs = admin_client.get("/api/admin/jobs", headers=admin_headers)
    assert jobs.status_code == 200, jobs.text
    rejected = [j for j in jobs.json() if j["status"] == "rejected"]
    assert any(j["workspace_name"] is None for j in rejected)


def test_accepted_index_is_not_journaled_as_rejection(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
    pg_container: str,
) -> None:
    key = _key(admin_client, admin_headers, "ws_journal_ok")
    r = admin_client.post(
        "/api/v1/index",
        headers={"Authorization": f"Bearer {key}"},
        json={"workspace": "ws_journal_ok", "path": "a.md", "content": "x"},
    )
    assert r.status_code == 202

    async def check() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            n = await conn.fetchval(
                "SELECT count(*) FROM ingestion_rejections WHERE workspace = 'ws_journal_ok'"
            )
        finally:
            await conn.close()
        assert n == 0  # une acceptation ne crée PAS de rejet

    asyncio.run(check())
