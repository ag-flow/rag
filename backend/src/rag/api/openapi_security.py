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
                    op["security"] = [{"BearerApiKey": []}]
        app.openapi_schema = schema
        return schema

    app.openapi = custom  # type: ignore[method-assign]
