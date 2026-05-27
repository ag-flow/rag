from __future__ import annotations

import uuid

import asyncpg
import pytest

from rag.db.workspace_migrations import apply_pending_for_all_workspaces
from rag.db.workspace_schema import derive_workspace_dsn


@pytest.mark.asyncio
async def test_boot_scan_applies_pending_workspace_migrations(
    migrated: asyncpg.Pool,
    admin_dsn: str,
) -> None:
    """Le boot scan applique migration 001 sur les workspaces 'legacy'.

    Setup : 2 workspaces seedés avec bases 'legacy' (sans `metadata`).
    Action : apply_pending_for_all_workspaces.
    Vérification : les 2 bases ont `metadata` column + workspace_schema_migrations à v=1.
    """
    from tests.integration._workspace_seed import seed_workspace

    # 2 bases legacy
    bases: list[tuple[str, str]] = []
    for i in range(2):
        name = f"rag_boot_scan_{uuid.uuid4().hex[:12]}"
        bases.append((name, derive_workspace_dsn(admin_dsn, name)))
        conn = await asyncpg.connect(admin_dsn)
        try:
            await conn.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
            await conn.execute(f'CREATE DATABASE "{name}"')
        finally:
            await conn.close()
        conn = await asyncpg.connect(bases[i][1])
        try:
            await conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
            await conn.execute(
                "CREATE TABLE embeddings ("
                "id SERIAL PRIMARY KEY, path TEXT NOT NULL, chunk_index INT NOT NULL, "
                "content TEXT NOT NULL, embedding vector(8) NOT NULL, "
                "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "UNIQUE (path, chunk_index))"
            )
        finally:
            await conn.close()

    try:
        # Seed workspaces
        async with migrated.acquire() as conn:
            for i, (name, dsn) in enumerate(bases):
                await seed_workspace(
                    conn,
                    name=f"ws_boot_{i}",
                    api_key=f"boot-key-{i}",
                    rag_cnx=dsn,
                    rag_base=name,
                )

        # Action
        await apply_pending_for_all_workspaces(migrated)

        # Vérifications
        for name, dsn in bases:
            conn = await asyncpg.connect(dsn)
            try:
                version = await conn.fetchval(
                    "SELECT MAX(version) FROM workspace_schema_migrations"
                )
                assert version == 1, f"{name}: expected version=1, got {version}"
                cols = {
                    r["column_name"]
                    for r in await conn.fetch(
                        "SELECT column_name FROM information_schema.columns "
                        "WHERE table_name = 'embeddings'"
                    )
                }
                assert "metadata" in cols, f"{name}: metadata column missing"
            finally:
                await conn.close()
    finally:
        admin = await asyncpg.connect(admin_dsn)
        try:
            for name, _ in bases:
                await admin.execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            await admin.close()


@pytest.mark.asyncio
async def test_boot_scan_fail_fast_on_unreachable_workspace(
    migrated: asyncpg.Pool,
) -> None:
    """Si une base workspace est inaccessible, apply_pending_for_all_workspaces raise."""
    from tests.integration._workspace_seed import seed_workspace

    async with migrated.acquire() as conn:
        await seed_workspace(
            conn,
            name="ws_boot_broken",
            api_key="broken-key",
            rag_cnx="postgresql://nope:nope@127.0.0.1:1/nope",
            rag_base="nope",
        )

    # asyncpg lève OSError / ConnectionError sur DSN injoignable ; on accepte
    # la classe parente OSError plutôt qu'`Exception` (cf. B017 — pas de blind
    # catch) tout en restant tolérant à la sous-classe précise retournée par
    # asyncpg/Python.
    with pytest.raises(OSError):
        await apply_pending_for_all_workspaces(migrated)
