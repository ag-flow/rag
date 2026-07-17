from __future__ import annotations

from fastapi.testclient import TestClient


def _create(client: TestClient, headers: dict[str, str], **body: object) -> dict:
    payload = {"label": "Ma stratégie", "algo": "prose", **body}
    resp = client.post("/api/admin/chunking/strategies", headers=headers, json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_parsers_listed(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    resp = admin_client.get("/api/admin/chunking/parsers", headers=admin_headers)
    assert resp.status_code == 200
    assert {"slug": "markdown", "label": "Markdown"} in resp.json()


def test_list_includes_system_strategies(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    resp = admin_client.get("/api/admin/chunking/strategies", headers=admin_headers)
    assert resp.status_code == 200
    by_slug = {s["slug"]: s for s in resp.json()}
    assert by_slug["markdown-deep"]["is_system"] is True
    assert by_slug["markdown-deep"]["used_by_categories"] >= 1


def test_create_derives_slug_and_conflicts(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = _create(admin_client, admin_headers, label="Prose API (été)")
    assert created["slug"] == "prose-api-ete"
    assert created["is_system"] is False
    assert created["routes"] == []
    dup = admin_client.post(
        "/api/admin/chunking/strategies",
        headers=admin_headers,
        json={"label": "Prose  API   été", "algo": "prose"},
    )
    assert dup.status_code == 409


def test_patch_rename_and_system_immutable(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = _create(admin_client, admin_headers, label="À renommer")
    patched = admin_client.patch(
        f"/api/admin/chunking/strategies/{created['id']}",
        headers=admin_headers,
        json={"label": "Renommée API"},
    )
    assert patched.status_code == 200
    assert patched.json()["slug"] == "renommee-api"

    strategies = admin_client.get("/api/admin/chunking/strategies", headers=admin_headers).json()
    system_id = next(s["id"] for s in strategies if s["is_system"])
    forbidden = admin_client.patch(
        f"/api/admin/chunking/strategies/{system_id}",
        headers=admin_headers,
        json={"label": "Pirate"},
    )
    assert forbidden.status_code == 403


def test_routes_roundtrip_and_delete_guard(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    target = _create(admin_client, admin_headers, label="Cible routes API")
    router = _create(admin_client, admin_headers, label="Routeur API", parser_slug="markdown")
    put = admin_client.put(
        f"/api/admin/chunking/strategies/{router['id']}/routes",
        headers=admin_headers,
        json={
            "routes": [
                {
                    "region_type": "code_fence",
                    "qualifier": "mermaid",
                    "target_strategy_id": target["id"],
                    "overflow_policy": "parent_only",
                },
                {"region_type": "table", "atomic": True},
            ]
        },
    )
    assert put.status_code == 200, put.text
    assert len(put.json()) == 2

    detail = admin_client.get(
        f"/api/admin/chunking/strategies/{router['id']}", headers=admin_headers
    ).json()
    assert len(detail["routes"]) == 2

    blocked = admin_client.delete(
        f"/api/admin/chunking/strategies/{target['id']}", headers=admin_headers
    )
    assert blocked.status_code == 409

    assert (
        admin_client.delete(
            f"/api/admin/chunking/strategies/{router['id']}", headers=admin_headers
        ).status_code
        == 204
    )
    assert (
        admin_client.delete(
            f"/api/admin/chunking/strategies/{target['id']}", headers=admin_headers
        ).status_code
        == 204
    )


def test_duplicate_copies_routes(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    source = _create(admin_client, admin_headers, label="Source dup API", parser_slug="markdown")
    admin_client.put(
        f"/api/admin/chunking/strategies/{source['id']}/routes",
        headers=admin_headers,
        json={"routes": [{"region_type": "table", "atomic": True}]},
    )
    copy = admin_client.post(
        f"/api/admin/chunking/strategies/{source['id']}/duplicate",
        headers=admin_headers,
        json={"label": "Copie dup API"},
    )
    assert copy.status_code == 201
    body = copy.json()
    assert body["slug"] == "copie-dup-api"
    assert body["parser_slug"] == "markdown"
    assert [r["region_type"] for r in body["routes"]] == ["table"]


def test_invalid_specs_rejected(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    bad_algo = admin_client.post(
        "/api/admin/chunking/strategies",
        headers=admin_headers,
        json={"label": "Quantum", "algo": "quantum"},
    )
    assert bad_algo.status_code == 422
    parser_on_table = admin_client.post(
        "/api/admin/chunking/strategies",
        headers=admin_headers,
        json={"label": "Table régions", "algo": "table", "parser_slug": "markdown"},
    )
    assert parser_on_table.status_code == 422
