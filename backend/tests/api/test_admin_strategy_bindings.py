from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient


def _make_ws(client: TestClient, headers: dict[str, str], name: str) -> dict:
    r = client.post(
        "/api/admin/workspaces",
        headers=headers,
        json={"name": name, "endpoint_id": client.default_endpoint_id},
    )
    assert r.status_code == 201, r.text
    return r.json()


def _make_strategy(client: TestClient, headers: dict[str, str], label: str) -> dict:
    r = client.post(
        "/api/admin/chunking/strategies",
        headers=headers,
        json={"label": label, "algo": "prose"},
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_default_strategy_set_clear_and_no_change(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "bind-default")
    strategy = _make_strategy(admin_client, admin_headers, "Défaut binding A")
    url = "/api/admin/workspaces/bind-default/chunking-config/default-strategy"

    # 0 doc indexé → bascule immédiate (200).
    set_resp = admin_client.put(url, headers=admin_headers, json={"strategy_id": strategy["id"]})
    assert set_resp.status_code == 200, set_resp.text
    assert set_resp.json()["default_strategy_id"] == strategy["id"]

    # Idempotent → 204.
    again = admin_client.put(url, headers=admin_headers, json={"strategy_id": strategy["id"]})
    assert again.status_code == 204

    # Visible dans le GET chunking-config.
    cfg = admin_client.get(
        "/api/admin/workspaces/bind-default/chunking-config", headers=admin_headers
    )
    assert cfg.json()["default_strategy_id"] == strategy["id"]

    # La stratégie expose le compteur workspace.
    listed = admin_client.get("/api/admin/chunking/strategies", headers=admin_headers).json()
    entry = next(s for s in listed if s["id"] == strategy["id"])
    assert entry["used_by_workspaces"] == 1

    # Suppression refusée tant que liée.
    blocked = admin_client.delete(
        f"/api/admin/chunking/strategies/{strategy['id']}", headers=admin_headers
    )
    assert blocked.status_code == 409

    # NULL retire le binding.
    cleared = admin_client.put(url, headers=admin_headers, json={"strategy_id": None})
    assert cleared.status_code == 200
    assert cleared.json()["default_strategy_id"] is None


def test_default_strategy_unknown_id_422(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "bind-default-bad")
    resp = admin_client.put(
        "/api/admin/workspaces/bind-default-bad/chunking-config/default-strategy",
        headers=admin_headers,
        json={"strategy_id": str(uuid4())},
    )
    assert resp.status_code == 422


def test_trigger_strategy_binding_roundtrip(
    admin_client: TestClient, admin_headers: dict[str, str], cleanup_ws_dbs_api: None
) -> None:
    _make_ws(admin_client, admin_headers, "bind-trigger")
    strategy = _make_strategy(admin_client, admin_headers, "Trigger binding A")

    created = admin_client.post(
        "/api/admin/workspaces/bind-trigger/triggers",
        headers=admin_headers,
        json={"extension": ".md", "strategy_id": strategy["id"]},
    )
    assert created.status_code == 201, created.text
    trigger = created.json()
    assert trigger["strategy_id"] == strategy["id"]

    # Compteur exposé côté stratégie.
    listed = admin_client.get("/api/admin/chunking/strategies", headers=admin_headers).json()
    entry = next(s for s in listed if s["id"] == strategy["id"])
    assert entry["used_by_triggers"] == 1

    # Patch : retirer le binding (null explicite).
    patched = admin_client.patch(
        f"/api/admin/workspaces/bind-trigger/triggers/{trigger['id']}",
        headers=admin_headers,
        json={"strategy_id": None},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["strategy_id"] is None

    # Stratégie inconnue → 422.
    bad = admin_client.patch(
        f"/api/admin/workspaces/bind-trigger/triggers/{trigger['id']}",
        headers=admin_headers,
        json={"strategy_id": str(uuid4())},
    )
    assert bad.status_code == 422
