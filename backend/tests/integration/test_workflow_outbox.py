"""Outbox transactionnel des events workflow (migration 069) — transitions."""

from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db import workflow_outbox
from rag.db.migrations import run_migrations

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


async def _prepare(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM workflow_event_outbox")


@pytest.mark.asyncio
async def test_enqueue_then_claim_due(session_pool: asyncpg.Pool) -> None:
    await _prepare(session_pool)
    async with session_pool.acquire() as conn:
        eid = await workflow_outbox.enqueue(
            conn, event_code="rag.workspace.created.v1", payload=b"{}"
        )
        due = await workflow_outbox.claim_due(conn)
    assert any(e.id == eid and e.event_code == "rag.workspace.created.v1" for e in due)


@pytest.mark.asyncio
async def test_mark_delivered_removes_from_due(session_pool: asyncpg.Pool) -> None:
    await _prepare(session_pool)
    async with session_pool.acquire() as conn:
        eid = await workflow_outbox.enqueue(conn, event_code="c", payload=b"{}")
        await workflow_outbox.mark_delivered(conn, entry_id=eid)
        due = await workflow_outbox.claim_due(conn)
        status = await conn.fetchval("SELECT status FROM workflow_event_outbox WHERE id=$1", eid)
    assert status == "delivered"
    assert all(e.id != eid for e in due)


@pytest.mark.asyncio
async def test_mark_retry_pushes_next_attempt_forward(session_pool: asyncpg.Pool) -> None:
    await _prepare(session_pool)
    async with session_pool.acquire() as conn:
        eid = await workflow_outbox.enqueue(conn, event_code="c", payload=b"{}")
        await workflow_outbox.mark_retry(conn, entry_id=eid, attempts=0, error="http 500")
        # next_attempt_at repoussé (~30 s) → plus dû immédiatement.
        due = await workflow_outbox.claim_due(conn)
        row = await conn.fetchrow(
            "SELECT status, attempts, last_error, next_attempt_at > now() AS future "
            "FROM workflow_event_outbox WHERE id=$1",
            eid,
        )
    assert row["status"] == "pending" and row["attempts"] == 1
    assert row["last_error"] == "http 500" and row["future"] is True
    assert all(e.id != eid for e in due)


@pytest.mark.asyncio
async def test_mark_failed_is_terminal(session_pool: asyncpg.Pool) -> None:
    await _prepare(session_pool)
    async with session_pool.acquire() as conn:
        eid = await workflow_outbox.enqueue(conn, event_code="c", payload=b"{}")
        await workflow_outbox.mark_failed(conn, entry_id=eid, error="max attempts")
        due = await workflow_outbox.claim_due(conn)
        status = await conn.fetchval("SELECT status FROM workflow_event_outbox WHERE id=$1", eid)
    assert status == "failed"
    assert all(e.id != eid for e in due)


@pytest.mark.asyncio
async def test_purge_delivered_removes_old(session_pool: asyncpg.Pool) -> None:
    await _prepare(session_pool)
    async with session_pool.acquire() as conn:
        eid = await workflow_outbox.enqueue(conn, event_code="c", payload=b"{}")
        await conn.execute(
            "UPDATE workflow_event_outbox SET status='delivered', "
            "delivered_at = now() - interval '48 hours' WHERE id=$1",
            eid,
        )
        purged = await workflow_outbox.purge_delivered(conn, older_than_hours=24)
        exists = await conn.fetchval("SELECT 1 FROM workflow_event_outbox WHERE id=$1", eid)
    assert purged >= 1 and exists is None
