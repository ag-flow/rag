from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


def _ws_key(
    client: TestClient, admin_headers: dict[str, str], name: str, *, scope: str = "read"
) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def test_read_endpoints_reject_missing_bearer(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _ws_key(admin_client, admin_headers, "wq_noauth")
    r = admin_client.get("/workspaces/wq_noauth/index-status")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_read_endpoints_reject_invalid_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _ws_key(admin_client, admin_headers, "wq_badkey")
    r = admin_client.get(
        "/workspaces/wq_badkey/index-status",
        headers={"Authorization": "Bearer not-a-real-key"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_read_scope_key_is_accepted(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Le cœur de la Phase 0 : une clé de niveau `read` accède aux endpoints de lecture."""
    key = _ws_key(admin_client, admin_headers, "wq_read", scope="read")
    r = admin_client.get(
        "/workspaces/wq_read/index-status",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace"] == "wq_read"
    assert body["documents_count"] == 0


def test_index_status_document_not_indexed_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_docstatus")
    r = admin_client.get(
        "/workspaces/wq_docstatus/index-status",
        params={"path": "missing.md"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "document_not_indexed"


def test_files_search_empty_returns_zero(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_files")
    r = admin_client.get(
        "/workspaces/wq_files/files",
        params={"pattern": "anything"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0
    assert body["hits"] == []


def test_document_not_indexed_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_doc")
    r = admin_client.get(
        "/workspaces/wq_doc/documents/nope.md",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "document_not_indexed"


def test_enrichment_not_found_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_enrich")
    r = admin_client.get(
        "/workspaces/wq_enrich/enrichments/some/file.py",
        params={"key": "summary"},
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "enrichment_not_found"


def test_jobs_list_empty_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_jobs")
    r = admin_client.get(
        "/workspaces/wq_jobs/jobs", headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_job_status_unknown_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_jobstat")
    r = admin_client.get(
        "/workspaces/wq_jobstat/jobs/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "job_not_found"


def test_chunking_config_read_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """La chunking-config est hydratée à la création du workspace → 200 avec l'algo."""
    key = _ws_key(admin_client, admin_headers, "wq_chunk")
    r = admin_client.get(
        "/workspaces/wq_chunk/chunking-config",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "strategy" in body
    assert "engine" in body
