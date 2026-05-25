from __future__ import annotations

import json
from uuid import UUID

import asyncpg
import pytest

from rag.api.errors import ChunkingConfigNotFound
from rag.schemas.admin import ChunkingConfigSpec
from rag.services.chunking_configs import (
    get_chunking_config,
    upsert_chunking_config,
)
from tests.integration._workspace_seed import seed_workspace


@pytest.fixture
async def workspace_id(migrated: asyncpg.Pool) -> UUID:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(conn, name="ws_chunking_svc")
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars) "
            "VALUES ($1, 'paragraph', 2000, 200, 200)",
            ws_id,
        )
    return ws_id


@pytest.mark.asyncio
async def test_get_returns_row(migrated: asyncpg.Pool, workspace_id: UUID) -> None:
    cfg = await get_chunking_config(workspace_id, migrated)
    assert cfg["strategy"] == "paragraph"
    assert cfg["max_chars"] == 2000
    assert cfg["min_chars"] == 200
    assert cfg["overlap_chars"] == 200
    assert cfg["extras"] == {}


@pytest.mark.asyncio
async def test_get_raises_when_missing(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        orphan_ws_id = await seed_workspace(
            conn,
            name="ws_no_config",
            api_key="orphan-key",
        )
    with pytest.raises(ChunkingConfigNotFound):
        await get_chunking_config(orphan_ws_id, migrated)


@pytest.mark.asyncio
async def test_upsert_updates_existing(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1500,
        min_chars=100,
        overlap_chars=150,
        extras={},
    )
    cfg = await upsert_chunking_config(
        workspace_id=workspace_id,
        spec=spec,
        config_pool=migrated,
    )
    assert cfg["max_chars"] == 1500
    assert cfg["min_chars"] == 100
    assert cfg["overlap_chars"] == 150


@pytest.mark.asyncio
async def test_upsert_inserts_when_absent(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        ws_id = await seed_workspace(
            conn,
            name="ws_upsert_new",
            api_key="upsert-new-key",
        )
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=800,
        min_chars=80,
        overlap_chars=80,
        extras={},
    )
    cfg = await upsert_chunking_config(
        workspace_id=ws_id,
        spec=spec,
        config_pool=migrated,
    )
    assert cfg["max_chars"] == 800


@pytest.mark.asyncio
async def test_upsert_updates_updated_at(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    now_before = await migrated.fetchval("SELECT now()")
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1234,
        min_chars=100,
        overlap_chars=100,
        extras={},
    )
    cfg_after = await upsert_chunking_config(
        workspace_id=workspace_id,
        spec=spec,
        config_pool=migrated,
    )
    assert cfg_after["updated_at"] > now_before


@pytest.mark.asyncio
async def test_fk_cascade_on_workspace_delete(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    async with migrated.acquire() as conn:
        await conn.execute("DELETE FROM workspaces WHERE id = $1", workspace_id)
        count = await conn.fetchval(
            "SELECT COUNT(*) FROM chunking_configs WHERE workspace_id = $1",
            workspace_id,
        )
    assert count == 0


@pytest.mark.asyncio
async def test_upsert_extras_default_empty_dict(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """extras=None / {} both roundtrip as {}."""
    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=500,
        min_chars=50,
        overlap_chars=50,
        extras={},
    )
    cfg = await upsert_chunking_config(
        workspace_id=workspace_id,
        spec=spec,
        config_pool=migrated,
    )
    assert cfg["extras"] == {}


@pytest.mark.asyncio
async def test_upsert_extras_round_trip_with_content(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """Non-empty extras roundtrip via json.dumps / json.loads."""
    # Note : bypass du DTO (qui forbid extras non vide pour strategy='paragraph')
    # via raw update pour préparer une row avec extras populée, puis re-lire via get.
    await migrated.execute(
        "UPDATE chunking_configs SET extras = $1::jsonb WHERE workspace_id = $2",
        json.dumps({"foo": "bar", "n": 42}),
        workspace_id,
    )
    cfg = await get_chunking_config(workspace_id, migrated)
    assert cfg["extras"] == {"foo": "bar", "n": 42}


# --- apply_chunking_change (M9-T7) ---------------------------------------


@pytest.mark.asyncio
async def test_apply_chunking_change_no_change_returns_no_change(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """Payload identique à la config courante → 'no_change' (caller 204)."""
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=2000,
        min_chars=200,
        overlap_chars=200,
        extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc",
        payload=spec,
        confirm=False,
        config_pool=migrated,
    )
    assert result == "no_change"


@pytest.mark.asyncio
async def test_apply_chunking_change_no_docs_updates(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """Changement réel + 0 docs indexés → upsert sans reindex ('updated', cfg)."""
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1500,
        min_chars=100,
        overlap_chars=150,
        extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc",
        payload=spec,
        confirm=False,
        config_pool=migrated,
    )
    assert isinstance(result, tuple)
    tag, new_cfg = result
    assert tag == "updated"
    assert new_cfg["max_chars"] == 1500
    assert new_cfg["min_chars"] == 100
    assert new_cfg["overlap_chars"] == 150


@pytest.mark.asyncio
async def test_apply_chunking_change_with_docs_raises_without_confirm(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """Changement réel + docs présents + !confirm → ChunkingChangeRequiresReindex."""
    from rag.api.errors import ChunkingChangeRequiresReindex
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, $2, $3, $4)",
        workspace_id,
        "a.md",
        "sha256:0",
        "ollama/x",
    )

    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1500,
        min_chars=100,
        overlap_chars=150,
        extras={},
    )
    with pytest.raises(ChunkingChangeRequiresReindex) as excinfo:
        await apply_chunking_change(
            name="ws_chunking_svc",
            payload=spec,
            confirm=False,
            config_pool=migrated,
        )
    # Le payload est bien renseigné (current + new humainement lisibles).
    assert "max=2000" in excinfo.value.current
    assert "max=1500" in excinfo.value.new


@pytest.mark.asyncio
async def test_apply_chunking_change_with_docs_and_confirm_triggers_reindex(
    migrated: asyncpg.Pool,
    workspace_id: UUID,
) -> None:
    """Changement réel + docs présents + confirm=True → upsert + job pending."""
    from rag.schemas.admin import ChunkingConfigSpec
    from rag.services.jobs import apply_chunking_change

    await migrated.execute(
        "INSERT INTO indexed_documents (workspace_id, path, content_hash, indexer_used) "
        "VALUES ($1, $2, $3, $4)",
        workspace_id,
        "b.md",
        "sha256:0",
        "ollama/x",
    )

    spec = ChunkingConfigSpec(
        strategy="paragraph",
        max_chars=1500,
        min_chars=100,
        overlap_chars=150,
        extras={},
    )
    result = await apply_chunking_change(
        name="ws_chunking_svc",
        payload=spec,
        confirm=True,
        config_pool=migrated,
    )
    assert isinstance(result, tuple)
    tag, job_row = result
    assert tag == "reindex_triggered"
    assert job_row["triggered_by"] == "reindex_chunking_change"
    assert job_row["status"] == "pending"

    # La nouvelle config est bien persistée (transaction atomique upsert+job).
    new_cfg = await migrated.fetchrow(
        "SELECT max_chars, min_chars, overlap_chars FROM chunking_configs WHERE workspace_id = $1",
        workspace_id,
    )
    assert new_cfg["max_chars"] == 1500
    assert new_cfg["min_chars"] == 100
    assert new_cfg["overlap_chars"] == 150
