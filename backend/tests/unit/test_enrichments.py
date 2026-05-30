from __future__ import annotations

from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from rag.services.enrichments import run_enrichments


def _make_conn(trigger_rows=None, enrichment_row=None):
    conn = MagicMock()
    conn.fetch = AsyncMock(return_value=trigger_rows or [])
    conn.fetchrow = AsyncMock(return_value=enrichment_row)
    conn.execute = AsyncMock(return_value="UPDATE 1")
    conn.fetchval = AsyncMock(return_value=None)
    return conn


def _trigger_row(
    template_id="00000000-0000-0000-0000-000000000001",
    llm_id="00000000-0000-0000-0000-000000000002",
    order_index=1,
    metadata_key="documentation",
    result_type="text",
    prompt="Génère la doc: {content}",
    llm_provider="openai",
    llm_model="gpt-4o",
    api_key_ref=None,
    llm_base_url=None,
):
    return {
        "template_id": template_id,
        "llm_id": llm_id,
        "order_index": order_index,
        "metadata_key": metadata_key,
        "result_type": result_type,
        "prompt": prompt,
        "llm_provider": llm_provider,
        "llm_model": llm_model,
        "api_key_ref": api_key_ref,
        "llm_base_url": llm_base_url,
        "template_name": "generate-doc",
    }


@pytest.mark.asyncio
async def test_run_enrichments_no_trigger() -> None:
    conn = _make_conn(trigger_rows=[])
    indexer = MagicMock()

    results = await run_enrichments(
        conn=conn,
        indexer=indexer,
        workspace_id="ws1",
        workspace_name="test-ws",
        path="src/main.rs",
        content="fn main() {}",
        content_hash="sha256:abc",
        vault_svc=MagicMock(),
        client_provider=MagicMock(),
    )

    assert results == []
    indexer.index_file.assert_not_called()


@pytest.mark.asyncio
async def test_run_enrichments_calls_llm_and_indexes() -> None:
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value=None)

    indexer = MagicMock()
    indexer.index_file = AsyncMock(return_value=1)

    with patch("rag.services.enrichments.call_llm", new=AsyncMock(return_value={
        "answer": "Documentation générée.", "usage": {"prompt_tokens": 100, "completion_tokens": 50}
    })):
        results = await run_enrichments(
            conn=conn,
            indexer=indexer,
            workspace_id="ws1",
            workspace_name="test-ws",
            path="src/service.cs",
            content="class Foo {}",
            content_hash="sha256:xyz",
            vault_svc=MagicMock(),
            client_provider=MagicMock(),
        )

    assert len(results) == 1
    assert results[0]["metadata_key"] == "documentation"
    assert results[0]["status"] == "done"
    indexer.index_file.assert_called_once()
    call_kwargs = indexer.index_file.call_args.kwargs
    assert call_kwargs["path"] == "src/service.cs::documentation"


@pytest.mark.asyncio
async def test_run_enrichments_skips_if_hash_unchanged() -> None:
    src_hash = sha256("class Foo {}".encode()).hexdigest()
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value={"result_hash": src_hash, "id": "enr1"})

    indexer = MagicMock()
    indexer.index_file = AsyncMock()

    results = await run_enrichments(
        conn=conn,
        indexer=indexer,
        workspace_id="ws1",
        workspace_name="test-ws",
        path="src/service.cs",
        content="class Foo {}",
        content_hash=f"sha256:{src_hash}",
        vault_svc=MagicMock(),
        client_provider=MagicMock(),
    )

    assert results[0]["status"] == "skipped"
    indexer.index_file.assert_not_called()


@pytest.mark.asyncio
async def test_run_enrichments_cleans_on_empty_result() -> None:
    conn = _make_conn(trigger_rows=[_trigger_row()])
    conn.fetchrow = AsyncMock(return_value={"result_hash": "old", "id": "enr1"})

    indexer = MagicMock()
    indexer.delete_file = AsyncMock()
    indexer.index_file = AsyncMock()

    with patch("rag.services.enrichments.call_llm", new=AsyncMock(return_value={
        "answer": "   ", "usage": {"prompt_tokens": 10, "completion_tokens": 0}
    })):
        results = await run_enrichments(
            conn=conn,
            indexer=indexer,
            workspace_id="ws1",
            workspace_name="test-ws",
            path="src/service.cs",
            content="changed content",
            content_hash="sha256:newHash",
            vault_svc=MagicMock(),
            client_provider=MagicMock(),
        )

    assert results[0]["status"] == "empty"
    indexer.delete_file.assert_called_once()
    indexer.index_file.assert_not_called()
