"""M5e-T9 — Guard lifespan : DEK requis si workspaces non vide.

Si la table `workspaces` contient au moins une ligne et que
`RAG_API_KEY_DEK` est absent de l'env, le lifespan doit lever
`RuntimeError` dès le démarrage pour éviter un mode dégradé silencieux
(impossible de déchiffrer les api_keys).

Si `workspaces` est vide, l'absence de DEK est tolérée.

Note : les tests utilisent `TestClient` dans `asyncio.to_thread` pour ne pas
bloquer la boucle asyncio. `TestClient` est synchrone + anyio-thread et
propage correctement les RuntimeError levées avant le yield du lifespan,
contrairement à `AsyncClient` avec `ASGITransport` dans Starlette 1.x.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

import asyncpg
import pytest
from fastapi.testclient import TestClient

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _base_env(monkeypatch) -> None:
    """Pose les env vars minimales pour que Settings() se charge sans lever."""
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("RAG_SESSION_SECRET", "s" * 32)
    # purge éventuelles paires Harpocrate de l'env
    monkeypatch.delenv("HARPOCRATE_API_TOKEN_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_API_URL_RAG", raising=False)
    monkeypatch.delenv("HARPOCRATE_DEK", raising=False)


@pytest.mark.asyncio
async def test_lifespan_fails_when_workspaces_exist_and_dek_absent(
    session_pool: asyncpg.Pool,
    pg_container: str,
    monkeypatch,
) -> None:
    """Si un workspace est présent en DB et que RAG_API_KEY_DEK est absent,
    le lifespan doit lever RuntimeError au démarrage (testé via TestClient)."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await seed_workspace(conn, name="ws_guard_test")

    _base_env(monkeypatch)
    # RAG_API_KEY_DEK explicitement absent
    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    # Pointer DATABASE_URL + ADMIN_URL sur la base test jetable
    monkeypatch.setenv("DATABASE_URL", pg_container)
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", pg_container.rsplit("/", 1)[0] + "/postgres")

    from rag.main import build_app

    app = build_app(migrations_dir=MIGRATIONS_DIR)

    # TestClient propage les RuntimeError levées avant le yield du lifespan.
    # On l'exécute via asyncio.to_thread pour ne pas bloquer la boucle asyncio
    # (TestClient est synchrone et utilise anyio en interne).
    # IMPORTANT : _start doit laisser l'exception se propager (pas de try/except
    # interne) pour que asyncio.to_thread la re-lève dans le contexte asyncio.
    def _start() -> None:
        with TestClient(app):
            pass

    with pytest.raises(RuntimeError, match="RAG_API_KEY_DEK"):
        await asyncio.to_thread(_start)


@pytest.mark.asyncio
async def test_lifespan_succeeds_when_workspaces_empty_and_dek_absent(
    session_pool: asyncpg.Pool,
    pg_container: str,
    monkeypatch,
) -> None:
    """Si la table workspaces est vide et que RAG_API_KEY_DEK est absent,
    le lifespan doit démarrer sans erreur."""
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workspaces")

    _base_env(monkeypatch)
    monkeypatch.delenv("RAG_API_KEY_DEK", raising=False)
    monkeypatch.setenv("DATABASE_URL", pg_container)
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", pg_container.rsplit("/", 1)[0] + "/postgres")

    from rag.main import build_app

    app = build_app(migrations_dir=MIGRATIONS_DIR)

    def _start() -> int:
        with TestClient(app) as client:
            return client.get("/health").status_code

    status = await asyncio.to_thread(_start)
    assert status == 200
