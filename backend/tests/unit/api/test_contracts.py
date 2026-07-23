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


def _client_with_apikey_routes() -> TestClient:
    """App minimale : routers taggués apikey (workspace, search) + contrats +
    un router admin factice pour prouver qu'il est EXCLU du contrat filtré."""
    from rag.api.mcp import build_mcp_router
    from rag.api.workspace import build_workspace_router

    app = FastAPI()
    app.include_router(build_workspace_router())
    app.include_router(build_mcp_router())
    app.include_router(build_contracts_router())

    @app.get("/api/admin/fake", tags=["admin"])
    async def _admin_fake() -> dict:  # session-authed en vrai — jamais dans le filtre
        return {}

    return TestClient(app)


class TestOpenApiApiKeyContract:
    def test_only_apikey_tagged_paths(self) -> None:
        resp = _client_with_apikey_routes().get("/api/contracts/openapi-apikey")

        assert resp.status_code == 200
        data = resp.json()
        assert data["openapi"].startswith("3.")
        # servers présent → l'outil consommateur connaît l'URL de base.
        assert data["servers"] and data["servers"][0]["url"]
        paths = data["paths"]
        # Les endpoints par clé API sont présents…
        assert "/api/v1/search" in paths
        assert any(p.endswith("/index") for p in paths)
        # …et AUCUN endpoint non-apikey (ex. l'endpoint admin factice).
        assert "/api/admin/fake" not in paths
        # chaque opération conservée porte bien le tag apikey
        for ops in paths.values():
            for op in ops.values():
                assert "apikey" in op["tags"]


class TestOpenApiSecurity:
    def _secured_client(self) -> TestClient:
        from rag.api.mcp import build_mcp_router
        from rag.api.openapi_security import install_openapi_security
        from rag.api.workspace import build_workspace_router

        app = FastAPI()
        app.include_router(build_workspace_router())
        app.include_router(build_mcp_router())
        app.include_router(build_contracts_router())

        @app.get("/api/admin/fake", tags=["admin"])
        async def _admin_fake() -> dict:
            return {}

        install_openapi_security(app)
        return TestClient(app)

    def test_bearer_scheme_declared_and_applied_to_apikey_ops(self) -> None:
        app_client = self._secured_client()
        spec = app_client.app.openapi()  # type: ignore[attr-defined]

        scheme = spec["components"]["securitySchemes"]["BearerApiKey"]
        assert scheme["type"] == "http"
        assert scheme["scheme"] == "bearer"

        # Une opération apikey porte la sécurité, l'admin factice non.
        assert spec["paths"]["/api/v1/search"]["post"]["security"] == [{"BearerApiKey": []}]
        assert spec["paths"]["/api/admin/fake"]["get"].get("security") is None

    def test_filtered_contract_inherits_security(self) -> None:
        resp = self._secured_client().get("/api/contracts/openapi-apikey")
        data = resp.json()

        assert "BearerApiKey" in data["components"]["securitySchemes"]
        for ops in data["paths"].values():
            for op in ops.values():
                assert op["security"] == [{"BearerApiKey": []}]


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
