from __future__ import annotations

from uuid import uuid4

from fastapi.testclient import TestClient

_DOC = "# Guide\n\nDe la prose.\n\n```mermaid\ngraph TD; A-->B;\n```\n\nSuite.\n"


def _create_strategy(client: TestClient, headers: dict[str, str], label: str) -> dict:
    resp = client.post(
        "/api/admin/chunking/strategies",
        headers=headers,
        json={"label": label, "algo": "prose"},
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


def test_preview_is_pure_and_returns_chunks(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    strategy = _create_strategy(admin_client, admin_headers, "Preview API")
    resp = admin_client.post(
        "/api/admin/chunking/preview",
        headers=admin_headers,
        json={"strategy_id": strategy["id"], "content": _DOC},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_chunks"] == len(body["chunks"]) > 0
    assert body["strategy"]["slug"] == "preview-api"
    assert all(c["chunk_hash"] for c in body["chunks"])


def test_preview_unknown_strategy_404(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    resp = admin_client.post(
        "/api/admin/chunking/preview",
        headers=admin_headers,
        json={"strategy_id": str(uuid4()), "content": "# Doc"},
    )
    assert resp.status_code == 404


def test_compare_two_strategies_reports_diff(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    a = _create_strategy(admin_client, admin_headers, "Compare A")
    b = _create_strategy(admin_client, admin_headers, "Compare B")
    resp = admin_client.post(
        "/api/admin/chunking/preview/compare",
        headers=admin_headers,
        json={"strategy_a": a["id"], "strategy_b": b["id"], "content": _DOC},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["a"]["strategy"]["slug"] == "compare-a"
    assert body["b"]["strategy"]["slug"] == "compare-b"
    # Mêmes params par défaut → découpage identique, diff vide.
    assert body["diff"]["only_a"] == body["diff"]["only_b"] == []
    assert body["diff"]["common"] > 0
