from __future__ import annotations

from fastapi.testclient import TestClient

from tests.api._helpers import make_ws_with_user_key


def _key(
    client: TestClient, admin_headers: dict[str, str], name: str, *, scope: str = "read"
) -> str:
    _, api_key = make_ws_with_user_key(client, admin_headers, name, scope=scope)
    return api_key


def test_list_strategies_requires_bearer(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    r = admin_client.get("/api/library/strategies")
    assert r.status_code == 401
    assert r.json()["detail"] == "missing_bearer_token"


def test_list_strategies_read_scope_ok(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _key(admin_client, admin_headers, "lib_read", scope="read")
    r = admin_client.get(
        "/api/library/strategies", headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 200, r.text
    # Au minimum les stratégies système (owner NULL) sont visibles.
    assert isinstance(r.json(), list)


def test_list_parsers_read_scope_ok(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _key(admin_client, admin_headers, "lib_parsers", scope="read")
    r = admin_client.get(
        "/api/library/parsers", headers={"Authorization": f"Bearer {key}"}
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json(), list)


def test_create_requires_admin_scope(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    """Une clé read_write ne suffit pas : les mutations exigent le scope admin."""
    key = _key(admin_client, admin_headers, "lib_rw", scope="read_write")
    r = admin_client.post(
        "/api/library/strategies",
        headers={"Authorization": f"Bearer {key}"},
        json={"label": "Ma stratégie", "algo": "prose"},
    )
    assert r.status_code == 403
    assert r.json()["detail"] == "admin_scope_required"


def test_admin_scope_can_create_and_get(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _key(admin_client, admin_headers, "lib_admin", scope="admin")
    headers = {"Authorization": f"Bearer {key}"}
    created = admin_client.post(
        "/api/library/strategies",
        headers=headers,
        json={"label": "Docs internes", "algo": "prose"},
    )
    assert created.status_code == 201, created.text
    sid = created.json()["id"]

    got = admin_client.get(f"/api/library/strategies/{sid}", headers=headers)
    assert got.status_code == 200
    assert got.json()["label"] == "Docs internes"


def test_get_unknown_strategy_returns_404(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    key = _key(admin_client, admin_headers, "lib_404", scope="read")
    r = admin_client.get(
        "/api/library/strategies/00000000-0000-0000-0000-000000000000",
        headers={"Authorization": f"Bearer {key}"},
    )
    assert r.status_code == 404
