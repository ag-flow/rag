"""Helpers de construction de TestClient pour les tests API.

Les test files importent `make_app_client` plutôt que de dupliquer le bloc
os.environ. Garder l'env setup en un seul endroit évite la dérive.
"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi.testclient import TestClient

from rag.main import build_app

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def make_app_client(
    pg_container: str,
    *,
    ttl_seconds: int | None = None,
) -> TestClient:
    """Construit un TestClient avec les env vars nécessaires.

    - `ttl_seconds` override le TTL session locale (1s en test d'expiration).
    """
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.setdefault("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    os.environ.setdefault("ENVIRONMENT", "dev")
    if ttl_seconds is not None:
        os.environ["RAG_LOCAL_SESSION_TTL_SECONDS"] = str(ttl_seconds)
    else:
        os.environ.pop("RAG_LOCAL_SESSION_TTL_SECONDS", None)

    app = build_app(version="0.2.0", git_sha="testsha", migrations_dir=MIGRATIONS_DIR)
    return TestClient(app)


def make_ws_with_user_key(
    client: TestClient,
    admin_headers: dict[str, str],
    name: str,
    *,
    can_read: bool = True,
    can_write: bool = True,
) -> tuple[dict, str]:
    """Crée un workspace + une clé API utilisateur avec grant. → (workspace, clé).

    Remplace l'ancien flux « la création de workspace retourne une api_key »
    (supprimé par le chantier clés utilisateur, 444308a) : l'accès push/MCP
    passe par une clé user (`/api/me/api-keys`) avec grants par workspace.
    """
    ws = client.post(
        "/api/admin/workspaces",
        headers=admin_headers,
        json={"name": name, "endpoint_id": client.default_endpoint_id},  # type: ignore[attr-defined]
    )
    assert ws.status_code == 201, ws.text
    key = client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={
            "name": f"key-{name}",
            "workspaces": [
                {
                    "workspace_id": ws.json()["id"],
                    "can_read": can_read,
                    "can_write": can_write,
                }
            ],
        },
    )
    assert key.status_code == 201, key.text
    return ws.json(), key.json()["api_key"]
