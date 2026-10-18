from __future__ import annotations

from typing import Any

from fastapi import FastAPI

_BEARER_SCHEME: dict[str, Any] = {
    "type": "http",
    "scheme": "bearer",
    "description": (
        "Clé API utilisateur : en-tête `Authorization: Bearer <clé>`. "
        "Créée depuis l'IHM (Mes clés API) ou `POST /api/me/api-keys`. "
        "Le niveau de la clé (read / read_write / admin) détermine les "
        "opérations autorisées ; les lectures acceptent `read`, les écritures "
        "exigent `read_write`, la gestion de bibliothèque `admin`."
    ),
}

# En-têtes OBO (contrat d0e2dad3 v6) : lus bruts par `rag.auth.obo_resolver`,
# FastAPI ne peut donc pas les déduire. Sans cette déclaration, le contrat
# publié laissait croire qu'une route clé API ignorait l'identité humaine.
_OBO_HEADERS: list[dict[str, Any]] = [
    {
        "name": "x-portal-actor",
        "in": "header",
        "required": False,
        "schema": {"type": "string"},
        "description": "OBO — GUID d'identité de l'humain (users.identity), posé par le portail.",
    },
    {
        "name": "x-portal-actor-timestamp",
        "in": "header",
        "required": False,
        "schema": {"type": "string"},
        "description": "OBO — instant d'émission, unix secondes (fenêtre anti-rejeu 300 s).",
    },
    {
        "name": "x-portal-actor-signature",
        "in": "header",
        "required": False,
        "schema": {"type": "string"},
        "description": (
            "OBO — HMAC-SHA256 hex de `{actor}\\n{timestamp}`, secret = la clé API "
            "du Bearer de la même requête. Valide et connue : l'appel est attribué à "
            "l'humain ; sinon à la clé — sauf clé « OBO obligatoire » : 401."
        ),
    },
]

_UNAUTHORIZED: dict[str, Any] = {
    "description": (
        "Clé absente ou invalide (`missing_bearer_token`, `invalid_auth_scheme`, "
        "`invalid_apikey`, `insufficient_scope`), ou clé « OBO obligatoire » sans "
        "identité signée valide et connue (`obo_required`)."
    )
}


def _declare_apikey_operation(op: dict[str, Any]) -> None:
    op["security"] = [{"BearerApiKey": []}]
    declared = {(p.get("in"), p.get("name")) for p in op.get("parameters", [])}
    params = op.setdefault("parameters", [])
    params.extend(h for h in _OBO_HEADERS if ("header", h["name"]) not in declared)
    op.setdefault("responses", {}).setdefault("401", _UNAUTHORIZED)


def install_openapi_security(app: FastAPI) -> None:
    """Déclare le scheme d'authentification par clé API et l'applique aux
    opérations taguées `apikey`.

    FastAPI ne génère pas de `securityScheme` pour nos dépendances qui lisent
    l'en-tête `Authorization` à la main : on l'injecte dans le document OpenAPI.
    Le contrat filtré `/api/contracts/openapi-apikey` en hérite automatiquement
    (il recopie `components` et les opérations, qui portent alors `security`).
    """
    original = app.openapi

    def custom() -> dict[str, Any]:
        if app.openapi_schema:
            return app.openapi_schema
        schema = original()
        schemes = schema.setdefault("components", {}).setdefault("securitySchemes", {})
        schemes["BearerApiKey"] = _BEARER_SCHEME
        for path_item in schema.get("paths", {}).values():
            for op in path_item.values():
                if isinstance(op, dict) and "apikey" in (op.get("tags") or []):
                    _declare_apikey_operation(op)
        app.openapi_schema = schema
        return schema

    app.openapi = custom  # type: ignore[method-assign]
