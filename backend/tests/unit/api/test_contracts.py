"""Contrats d'API publics (/api/contracts) — accessibles sans authentification."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.contracts import build_contracts_router


def _client() -> TestClient:
    app = FastAPI()
    app.include_router(build_contracts_router())
    return TestClient(app)


class TestContractsIndex:
    def test_index_sans_auth_reference_rest_et_mcp(self) -> None:
        resp = _client().get("/api/contracts")

        assert resp.status_code == 200
        data = resp.json()
        assert data["rest"]["json"] == "/openapi.json"
        assert data["rest"]["swagger_ui"] == "/docs"
        assert data["mcp"]["tools"] == "/api/contracts/mcp-tools"
        assert data["workflow_events"]["json"] == "/api/contracts/workflow-events"


class TestWorkflowEventsContract:
    def test_openapi_webhooks_contract_sans_auth(self) -> None:
        resp = _client().get("/api/contracts/workflow-events")

        assert resp.status_code == 200
        data = resp.json()
        assert data["openapi"] == "3.1.0"
        # Une clé webhook par event, operationId sans le provider (workflow préfixe).
        assert "workspace.created" in data["webhooks"]
        op = data["webhooks"]["workspace.created"]["post"]
        assert op["operationId"] == "workspace.created.v1"
        schema = op["requestBody"]["content"]["application/json"]["schema"]
        assert "slug" in schema["properties"]
        # L'enveloppe (_…) n'est jamais décrite dans le data_schema métier.
        assert not any(k.startswith("_") for k in schema["properties"])


class TestMcpToolsContract:
    def test_schema_des_outils_sans_auth(self) -> None:
        resp = _client().get("/api/contracts/mcp-tools")

        assert resp.status_code == 200
        data = resp.json()
        assert data["format"] == "mcp-tools"
        assert data["count"] >= 17
        names = {t["name"] for t in data["tools"]}
        # Outils de recherche ET de gestion de bibliothèque présents.
        assert "rag_search" in names
        assert "create_chunking_strategy" in names
        assert "create_prompt_template" in names
        # Chaque outil est un contrat complet : description + schéma d'entrée.
        for tool in data["tools"]:
            assert tool["description"]
            assert "inputSchema" in tool
