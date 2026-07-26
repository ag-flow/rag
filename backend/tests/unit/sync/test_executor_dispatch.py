"""Jobs de réindexation sans source (`manual`/`reindex_*`) : dispatch vers
`_execute_reindex_job`, fan-out en jobs par source git et re-chunk des
documents poussés depuis la table workspace `source_documents`."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from rag.indexer.protocol import StoredSourceDocument
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


def _stored(path: str, content: str = "contenu") -> StoredSourceDocument:
    return StoredSourceDocument(
        path=path,
        content=content,
        content_hash="sha256:" + path,
        title=None,
        source_url=None,
    )


def _fake_pool(
    *,
    sources: list[dict[str, Any]] | None = None,
    dedup_rows: list[dict[str, Any] | None] | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        fetch=AsyncMock(return_value=sources or []),
        fetchrow=AsyncMock(side_effect=dedup_rows or []),
        execute=AsyncMock(),
    )


class TestSourcelessJobDispatch:
    @pytest.mark.asyncio
    @pytest.mark.parametrize(
        "triggered_by", ["reindex_chunking_change", "reindex_indexer_change", "manual"]
    )
    async def test_routed_to_reindex_executor(
        self, monkeypatch: pytest.MonkeyPatch, triggered_by: str
    ) -> None:
        job = _sourceless_job(triggered_by)
        reindex = AsyncMock()
        monkeypatch.setattr(executor, "pick_next_pending_job", AsyncMock(return_value=job))
        monkeypatch.setattr(executor, "_execute_reindex_job", reindex)
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
        reindex.assert_awaited_once()
        assert reindex.await_args.kwargs["job"] is job


class TestExecuteReindexJob:
    @pytest.mark.asyncio
    async def test_fan_out_one_job_per_git_source(self) -> None:
        job = _sourceless_job("reindex_chunking_change")
        src_a, src_b = uuid4(), uuid4()
        pool = _fake_pool(sources=[{"id": src_a}, {"id": src_b}])
        indexer = SimpleNamespace(stored_sources=AsyncMock(return_value=[]), index_file=AsyncMock())
        await executor._execute_reindex_job(job=job, config_pool=pool, indexer=indexer)

        inserts = [c for c in pool.execute.await_args_list if "INSERT INTO index_jobs" in c.args[0]]
        assert {c.args[2] for c in inserts} == {src_a, src_b}
        assert all(c.args[3] == "reindex_chunking_change" for c in inserts)
        done = pool.execute.await_args_list[-1]
        assert "status='done'" in done.args[0]

    @pytest.mark.asyncio
    async def test_rechunks_stored_documents_with_dedup_skip(self) -> None:
        job = _sourceless_job("reindex_chunking_change")
        unchanged = {
            "content_hash": "sha256:deja.md",
            "indexer_used": "openai/text-embedding-3-small",
        }
        pool = _fake_pool(dedup_rows=[unchanged, None])
        indexer = SimpleNamespace(
            stored_sources=AsyncMock(return_value=[_stored("deja.md"), _stored("a-refaire.md")]),
            index_file=AsyncMock(),
        )
        await executor._execute_reindex_job(job=job, config_pool=pool, indexer=indexer)

        indexer.index_file.assert_awaited_once()
        assert indexer.index_file.await_args.kwargs["path"] == "a-refaire.md"
        done = pool.execute.await_args_list[-1]
        assert done.args[2] == 1  # files_changed
        assert done.args[3] == 1  # files_skipped

    @pytest.mark.asyncio
    async def test_permanent_file_error_is_isolated(self) -> None:
        job = _sourceless_job("reindex_chunking_change")
        pool = _fake_pool(dedup_rows=[None, None])
        indexer = SimpleNamespace(
            stored_sources=AsyncMock(return_value=[_stored("poison.md"), _stored("ok.md")]),
            index_file=AsyncMock(side_effect=[ValueError("panic tree-sitter"), None]),
        )
        await executor._execute_reindex_job(job=job, config_pool=pool, indexer=indexer)

        assert indexer.index_file.await_count == 2
        done = pool.execute.await_args_list[-1]
        assert done.args[2] == 1  # seul ok.md compte en files_changed
        assert "status='done'" in done.args[0]

    @pytest.mark.asyncio
    async def test_transient_error_propagates_to_job_machinery(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        job = _sourceless_job("reindex_indexer_change")
        pool = _fake_pool(dedup_rows=[None])
        indexer = SimpleNamespace(
            stored_sources=AsyncMock(return_value=[_stored("doc.md")]),
            index_file=AsyncMock(side_effect=RuntimeError("rate limited")),
        )
        monkeypatch.setattr(executor, "classify_indexer_error", lambda _exc: "transient")
        with pytest.raises(RuntimeError, match="rate limited"):
            await executor._execute_reindex_job(job=job, config_pool=pool, indexer=indexer)
