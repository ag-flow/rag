"""Tests d'intégration M9-T6 : create_workspace hooks chunking_configs et
applique les migrations workspace (workspace_schema_migrations + metadata).
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import asyncpg
import pytest

from rag.db.workspace_migrations.runner import _list_versions
from rag.db.workspace_schema import derive_workspace_dsn, drop_workspace_database
from rag.schemas.admin import IndexerCreateSpec, WorkspaceCreateResolved
from rag.schemas.harpocrate_vaults import VaultSummary
from rag.services.chunking_configs import get_chunking_config
from rag.services.workspaces import create_workspace

# Dernière version workspace, dérivée du répertoire versions/ (source de vérité).
_LATEST = max(v for v, _ in _list_versions())


def _make_harpo_service() -> MagicMock:
    """Stub HarpocrateVaultsService : get_default (await par create_workspace)
    doit être un AsyncMock."""
    service = MagicMock()
    vault = MagicMock(spec=VaultSummary)
    vault.id = uuid4()
    vault.name = "rag"
    service.get_by_name = AsyncMock(return_value=vault)
    service.get_default = AsyncMock(return_value=vault)
    return service


class _NullResolver:
    """Resolver stub : ne sera jamais appelé car api_key_ref=None (Ollama)."""

    async def resolve_with_retry(self, ref: str) -> str:  # pragma: no cover
        raise AssertionError("resolver should not be called when api_key_ref is None")


async def _cleanup_workspace(migrated: asyncpg.Pool, admin_dsn: str, name: str) -> None:
    async with migrated.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT rag_base FROM workspaces WHERE name = $1",
            name,
        )
        if row:
            await drop_workspace_database(admin_dsn, row["rag_base"])
        await conn.execute("DELETE FROM workspaces WHERE name = $1", name)


def _make_request(name: str) -> WorkspaceCreateResolved:
    return WorkspaceCreateResolved(
        name=name,
        indexer=IndexerCreateSpec(
            provider="ollama",
            model="mxbai-embed-large",
            api_key_ref=None,
            base_url="http://stub:11434",
        ),
    )


@pytest.mark.asyncio
async def test_create_workspace_inserts_default_chunking_config(
    migrated: asyncpg.Pool,
    admin_dsn: str,
) -> None:
    """create_workspace insère une chunking_config par défaut (paragraph + valeurs plan)."""
    name = "ws_create_chunk"
    req = _make_request(name)
    try:
        ws = await create_workspace(
            request=req,
            config_pool=migrated,
            admin_dsn=admin_dsn,
            resolver=_NullResolver(),  # type: ignore[arg-type]
            harpocrate_vaults_service=_make_harpo_service(),
        )
        cfg = await get_chunking_config(ws["id"], migrated)
        assert cfg["strategy"] == "paragraph"
        assert cfg["max_chars"] == 2000
        assert cfg["min_chars"] == 200
        assert cfg["overlap_chars"] == 200
        assert cfg["extras"] == {}
    finally:
        await _cleanup_workspace(migrated, admin_dsn, name)


@pytest.mark.asyncio
async def test_create_workspace_applies_workspace_migrations(
    migrated: asyncpg.Pool,
    admin_dsn: str,
) -> None:
    """La base workspace a la colonne `metadata` + workspace_schema_migrations à jour."""
    name = "ws_create_meta"
    req = _make_request(name)
    try:
        ws = await create_workspace(
            request=req,
            config_pool=migrated,
            admin_dsn=admin_dsn,
            resolver=_NullResolver(),  # type: ignore[arg-type]
            harpocrate_vaults_service=_make_harpo_service(),
        )

        row = await migrated.fetchrow(
            "SELECT rag_base FROM workspaces WHERE id = $1",
            ws["id"],
        )
        assert row is not None
        ws_dsn = derive_workspace_dsn(admin_dsn, row["rag_base"])
        conn = await asyncpg.connect(ws_dsn)
        try:
            cols = {
                r["column_name"]
                for r in await conn.fetch(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'embeddings'"
                )
            }
            assert "metadata" in cols
            version = await conn.fetchval("SELECT MAX(version) FROM workspace_schema_migrations")
            assert version == _LATEST
        finally:
            await conn.close()
    finally:
        await _cleanup_workspace(migrated, admin_dsn, name)
