from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

# Le test nécessite Postgres (pg_container fixture)
pytestmark = pytest.mark.asyncio

# Calculé en dehors de toute coroutine (Path.resolve est synchrone — ASYNC240).
_MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


async def test_boot_workspaces_table_non_empty_and_no_vaults_raises_runtime_error(
    pg_container: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Si workspaces a des rows mais harpocrate_vaults est vide, le lifespan
    doit raise un RuntimeError explicite au boot.
    """
    from rag.main import build_app

    monkeypatch.setenv("DATABASE_URL", pg_container)
    monkeypatch.setenv(
        "RAG_POSTGRES_ADMIN_URL",
        pg_container.rsplit("/", 1)[0] + "/postgres",
    )
    monkeypatch.setenv("RAG_MASTER_KEY", "mk_test_padding_padding_padding_padding")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv(
        "HARPOCRATE_DEK",
        "passphrase-of-at-least-32-characters-long",
    )

    app = build_app(version="test", git_sha="testsha", migrations_dir=_MIGRATIONS_DIR)

    # Appliquer les migrations puis insérer un workspace fictif pour simuler
    # l'état "workspaces non vide + 0 coffre".
    conn = await asyncpg.connect(pg_container)
    try:
        from rag.db.migrations import run_migrations

        await run_migrations(conn, _MIGRATIONS_DIR)

        # Insérer un workspace fictif : api_key_ref et api_key_fingerprint
        # sont NOT NULL depuis les migrations 015 + 010.
        await conn.execute(
            """
            INSERT INTO workspaces (name, api_key_ref, api_key_fingerprint, rag_cnx, rag_base)
            VALUES (
                'test-orphan',
                '${vault://nonexistent:wsapi_test-orphan}',
                $1,
                'stub',
                'stub'
            )
            """,
            "a" * 64,
        )
        # NB : harpocrate_vaults reste vide.
    finally:
        await conn.close()

    # Le lifespan doit lever RuntimeError au boot.
    with pytest.raises(RuntimeError, match=r"workspaces|coffre|vault"):
        async with app.router.lifespan_context(app):
            pass  # boot doit échouer
