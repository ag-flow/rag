from __future__ import annotations

from fastapi.testclient import TestClient


def test_create_inline_chunk_template(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    resp = admin_client.post(
        "/api/admin/prompts",
        headers=admin_headers,
        json={
            "name": "contexte-chunk-api",
            "language": "markdown",
            "metadata_key": "chunk_context",
            "prompt": "Situe précisément cet extrait : {chunk}",
            "target": "chunk",
            "timing": "embedding_inline",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert (body["target"], body["timing"], body["prompt_version"]) == (
        "chunk",
        "embedding_inline",
        1,
    )


def test_create_region_template_and_patch_bumps_version(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    created = admin_client.post(
        "/api/admin/prompts",
        headers=admin_headers,
        json={
            "name": "description-mermaid-api",
            "language": "markdown",
            "metadata_key": "mermaid_desc",
            "prompt": "Décris ce diagramme : {chunk}",
            "target": "region:code_fence:mermaid",
            "timing": "embedding_inline",
        },
    )
    assert created.status_code == 201, created.text
    template_id = created.json()["id"]

    patched = admin_client.patch(
        f"/api/admin/prompts/{template_id}",
        headers=admin_headers,
        json={"prompt": "Décris précisément ce diagramme : {chunk}"},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["prompt_version"] == 2


def test_unsupported_combo_rejected_422(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    resp = admin_client.post(
        "/api/admin/prompts",
        headers=admin_headers,
        json={
            "name": "combo-invalide-api",
            "language": "markdown",
            "metadata_key": "x",
            "prompt": "{chunk}",
            "target": "chunk",
            "timing": "post_index_metadata",
        },
    )
    assert resp.status_code == 422
