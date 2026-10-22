"""scripts/purge-template-paths.sh contre une base de config migrée (ticket 14a62570).

Le psql du conteneur est remplacé par un psql local pointé sur la base jetable
(PSQL_CMD) ; le SQL exécuté est celui du script, sans réécriture.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "purge-template-paths.sh"

pytestmark = pytest.mark.skipif(shutil.which("psql") is None, reason="psql requis")


@pytest.fixture
async def pool(session_pool: asyncpg.Pool) -> asyncpg.Pool:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    return session_pool


async def _seed(pool: asyncpg.Pool) -> dict[str, UUID]:
    async with pool.acquire() as conn:
        ws_doc = await seed_workspace(conn, name="docflow-docs")
        ws_glob = await seed_workspace(conn, name="globals-docs", rag_base="rag_test_g")
        for ws_id, path in (
            (ws_doc, "docflow/{event.blockSlug}/0111"),
            (ws_doc, "docflow/{event.blockSlug}/0222"),
            (ws_glob, "globals/{event.blockSlug}/0333"),
            # Doivent survivre : bon chemin, variable ailleurs que le 2e segment.
            (ws_doc, "docflow/documentation/0111"),
            (ws_doc, "docflow/documentation/{event.blockSlug}"),
            (ws_doc, "notes/{event.blockSlug}/sub/0444"),
        ):
            await conn.execute(
                "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used)"
                " VALUES ($1, $2, 'sha256:x', 'openai/text-embedding-3-small')",
                ws_id,
                path,
            )
    return {"docflow-docs": ws_doc, "globals-docs": ws_glob}


def _run(dsn: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PSQL_CMD": f"psql -X -q -v ON_ERROR_STOP=1 {dsn}"}
    return subprocess.run(
        ["bash", str(SCRIPT), *args], env=env, capture_output=True, text=True, check=False
    )


async def _delete_jobs(pool: asyncpg.Pool) -> set[str]:
    rows = await pool.fetch(
        "SELECT j.path FROM index_jobs j JOIN delete_job_payloads p ON p.job_id = j.id"
        " WHERE j.triggered_by = 'delete' AND j.status = 'pending' AND p.path = j.path"
    )
    return {r["path"] for r in rows}


async def test_purge_dry_run_lists_only_polluted_paths_and_writes_nothing(
    pool: asyncpg.Pool, pg_container: str
) -> None:
    await _seed(pool)
    result = _run(pg_container)
    assert result.returncode == 0, result.stderr
    assert "docflow/{event.blockSlug}/0111" in result.stdout
    assert "globals/{event.blockSlug}/0333" in result.stdout
    assert "docflow/documentation/0111" not in result.stdout
    assert "notes/{event.blockSlug}/sub/0444" not in result.stdout
    assert await _delete_jobs(pool) == set()


async def test_purge_apply_enqueues_one_delete_job_per_polluted_path(
    pool: asyncpg.Pool, pg_container: str
) -> None:
    await _seed(pool)
    result = _run(pg_container, "--apply")
    assert result.returncode == 0, result.stderr
    assert await _delete_jobs(pool) == {
        "docflow/{event.blockSlug}/0111",
        "docflow/{event.blockSlug}/0222",
        "globals/{event.blockSlug}/0333",
    }


async def test_purge_apply_twice_does_not_enqueue_duplicates(
    pool: asyncpg.Pool, pg_container: str
) -> None:
    await _seed(pool)
    assert _run(pg_container, "--apply").returncode == 0
    assert _run(pg_container, "--apply").returncode == 0
    count = await pool.fetchval("SELECT count(*) FROM index_jobs WHERE triggered_by = 'delete'")
    assert count == 3


def test_purge_unknown_argument_fails_without_touching_db() -> None:
    result = subprocess.run(
        ["bash", str(SCRIPT), "--force"], capture_output=True, text=True, check=False
    )
    assert result.returncode == 1
    assert "Argument inconnu" in result.stderr
