"""Dispatch de `execute_next_pending_job` : un job de réindexation sans source
git (workspace push-only, ou fan-out par source non implémenté) doit être marqué
en erreur pédagogique — pas crasher dans `_execute_git_job` (KeyError: 'url')."""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rag.schemas.sync import JobToProcess
from rag.sync import executor


def _sourceless_job(triggered_by: str) -> JobToProcess:
    return JobToProcess(
        job_id=uuid4(),
        workspace_id=uuid4(),
        workspace_name="ws-push-only",
        source_id=None,
        source_config={},
        indexer_provider="openai",
        indexer_model="text-embedding-3-small",
        triggered_by=triggered_by,
        correlation_id=None,
    )


async def _run(monkeypatch: pytest.MonkeyPatch, job: JobToProcess) -> AsyncMock:
    marked = AsyncMock()
    monkeypatch.setattr(executor, "pick_next_pending_job", AsyncMock(return_value=job))
    monkeypatch.setattr(executor, "_mark_job_error", marked)
    monkeypatch.setattr(
        executor,
        "_execute_git_job",
        AsyncMock(side_effect=AssertionError("_execute_git_job ne doit pas être appelé")),
    )
    stub: Any = object()
    handled = await executor.execute_next_pending_job(
        config_pool=stub,
        storage=stub,
        indexer=stub,
        resolver=stub,
        client_provider=stub,
    )
    assert handled is True
    return marked


class TestSourcelessJobDispatch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "triggered_by", ["reindex_chunking_change", "reindex_indexer_change", "manual"]
    )
    async def test_marked_error_with_pedagogical_message(
        self, monkeypatch: pytest.MonkeyPatch, triggered_by: str
    ) -> None:
        job = _sourceless_job(triggered_by)
        marked = await _run(monkeypatch, job)
        marked.assert_awaited_once()
        message = marked.await_args.kwargs["error_message"]
        assert triggered_by in message
        assert "source git" in message
        assert "re-pouss" in message

    @pytest.mark.asyncio
    async def test_job_log_bus_receives_error_and_completion(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _sourceless_job("reindex_chunking_change")
        marked = AsyncMock()
        monkeypatch.setattr(executor, "pick_next_pending_job", AsyncMock(return_value=job))
        monkeypatch.setattr(executor, "_mark_job_error", marked)

        events: list[tuple[str, ...]] = []

        class _Bus:
            def publish(self, job_id: str, level: str, message: str) -> None:
                events.append(("publish", job_id, level, message))

            def complete(self, job_id: str, *, status: str) -> None:
                events.append(("complete", job_id, status))

        stub: Any = object()
        await executor.execute_next_pending_job(
            config_pool=stub,
            storage=stub,
            indexer=stub,
            resolver=stub,
            client_provider=stub,
            job_log_bus=_Bus(),  # type: ignore[arg-type]
        )
        kinds = [e[0] for e in events]
        assert kinds == ["publish", "complete"]
        assert events[0][2] == "error"
        assert "source git" in events[0][3]
        assert events[1][2] == "error"
