from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key

# Lectures : workspace en query param (?workspace=…), plus dans l'URL.


def _ws_key(
    client: TestClient, admin_headers: dict[str, str], name: str, *, scope: str = "read"
) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def _get(client: TestClient, path: str, *, key: str | None, params: dict) -> object:
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    return client.get(path, params=params, headers=headers)


def test_read_endpoints_reject_missing_bearer(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _ws_key(admin_client, admin_headers, "wq_noauth")
    r = _get(admin_client, "/api/v1/index-status", key=None, params={"workspace": "wq_noauth"})
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_read_endpoints_reject_invalid_key(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _ws_key(admin_client, admin_headers, "wq_badkey")
    r = _get(
        admin_client,
        "/api/v1/index-status",
        key="not-a-real-key",
        params={"workspace": "wq_badkey"},
    )
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_apikey"


def test_read_scope_key_is_accepted(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Une clé de niveau `read` accède aux endpoints de lecture."""
    key = _ws_key(admin_client, admin_headers, "wq_read", scope="read")
    r = _get(admin_client, "/api/v1/index-status", key=key, params={"workspace": "wq_read"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["workspace"] == "wq_read"
    assert body["documents_count"] == 0


def test_unknown_workspace_returns_401(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Clé valide mais workspace non visible → 401 uniforme."""
    key = _ws_key(admin_client, admin_headers, "wq_known")
    r = _get(admin_client, "/api/v1/index-status", key=key, params={"workspace": "ghost"})
    assert r.status_code == 401
    assert r.json()["detail"] == "invalid_workspace_apikey"


def test_index_status_document_not_indexed_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_docstatus")
    r = _get(
        admin_client,
        "/api/v1/index-status",
        key=key,
        params={"workspace": "wq_docstatus", "path": "missing.md"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "document_not_indexed"


def test_files_search_empty_returns_zero(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_files")
    r = _get(
        admin_client,
        "/api/v1/files",
        key=key,
        params={"workspace": "wq_files", "pattern": "anything"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["count"] == 0
    assert body["hits"] == []


def test_document_not_indexed_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_doc")
    r = _get(
        admin_client,
        "/api/v1/documents",
        key=key,
        params={"workspace": "wq_doc", "path": "nope.md"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "document_not_indexed"


def test_enrichment_not_found_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_enrich")
    r = _get(
        admin_client,
        "/api/v1/enrichments",
        key=key,
        params={"workspace": "wq_enrich", "path": "some/file.py", "key": "summary"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "enrichment_not_found"


def test_jobs_list_empty_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_jobs")
    r = _get(admin_client, "/api/v1/jobs", key=key, params={"workspace": "wq_jobs"})
    assert r.status_code == 200, r.text
    assert r.json() == []


def test_job_status_unknown_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_jobstat")
    r = _get(
        admin_client,
        "/api/v1/jobs/00000000-0000-0000-0000-000000000000",
        key=key,
        params={"workspace": "wq_jobstat"},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "job_not_found"


def test_chunking_config_read_returns_200(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """La chunking-config est hydratée à la création du workspace → 200 avec l'algo."""
    key = _ws_key(admin_client, admin_headers, "wq_chunk")
    r = _get(admin_client, "/api/v1/chunking-config", key=key, params={"workspace": "wq_chunk"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "strategy" in body
    assert "engine" in body


def test_rerank_not_configured_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_rerank")
    r = _get(admin_client, "/api/v1/rerank", key=key, params={"workspace": "wq_rerank"})
    assert r.status_code == 404
    assert r.json()["detail"] == "rerank_not_configured"


def test_hybrid_not_configured_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _ws_key(admin_client, admin_headers, "wq_hybrid")
    r = _get(admin_client, "/api/v1/hybrid-config", key=key, params={"workspace": "wq_hybrid"})
    assert r.status_code == 404
    assert r.json()["detail"] == "hybrid_not_configured"
