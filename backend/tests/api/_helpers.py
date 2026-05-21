"""Helpers de construction de TestClient pour les tests API bootstrap-admin.

Les test files importent `make_app_client` plutôt que de dupliquer le bloc
os.environ. Garder l'env setup en un seul endroit évite la dérive
(cf. revue T2 et T4).
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
    password_hash: str = "",
    username: str = "admin",
    ttl_seconds: int | None = None,
) -> TestClient:
    """Construit un TestClient avec les env vars nécessaires.

    - `password_hash=""` désactive le bootstrap (variant courant).
    - `ttl_seconds` override le TTL session locale (1s en test d'expiration).
    """
    os.environ["DATABASE_URL"] = pg_container
    os.environ["RAG_POSTGRES_ADMIN_URL"] = pg_container.rsplit("/", 1)[0] + "/postgres"
    os.environ["RAG_MASTER_KEY"] = "mk_test_e2e_padding_padding_padding_padding"
    os.environ.setdefault("RAG_PUBLIC_URL", "http://localhost:8000")
    os.environ.pop("HARPOCRATE_API_TOKEN_RAG", None)
    os.environ.pop("HARPOCRATE_API_URL_RAG", None)
    os.environ.setdefault("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    os.environ.setdefault("ENVIRONMENT", "dev")
    os.environ["RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH"] = password_hash
    os.environ["RAG_BOOTSTRAP_ADMIN_USERNAME"] = username
    if ttl_seconds is not None:
        os.environ["RAG_BOOTSTRAP_SESSION_TTL_SECONDS"] = str(ttl_seconds)
    else:
        # Ne PAS conserver une valeur "1" laissée par un test précédent → reset au défaut.
        os.environ.pop("RAG_BOOTSTRAP_SESSION_TTL_SECONDS", None)

    app = build_app(version="0.2.0", git_sha="testsha", migrations_dir=MIGRATIONS_DIR)
    return TestClient(app)
