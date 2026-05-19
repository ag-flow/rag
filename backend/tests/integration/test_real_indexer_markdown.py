"""Test M9c-T5 : E2E RealIndexer + strategy markdown.

Workspace configuré en markdown → chunks ont la metadata section_title/path/level.
"""

from __future__ import annotations

import json

import asyncpg
import pytest

from rag.db.pool import WorkspacePoolRegistry
from rag.db.workspace_schema import derive_workspace_dsn, drop_workspace_database
from rag.indexer.real import RealIndexer
from rag.schemas.admin import IndexerSpec, WorkspaceCreateRequest
from rag.services.workspaces import create_workspace

_TEST_DEK = "x" * 32


README_DEMO = """\
Welcome to the demo project.

# Installation

Install the package via pip.

## From PyPI

```bash
pip install demo
```

## From source

Clone the repo and run setup.

# Usage

Basic usage example.

```python
import demo
demo.run()
```

# Reference

API reference is auto-generated.
"""


class _StubProvider:
    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 8 for _ in texts]


class _NullResolver:
    async def resolve_with_retry(self, ref: str) -> str:  # pragma: no cover
        raise AssertionError("resolver should not be called when api_key_ref is None")


class _StubClientProvider:
    async def get_default_vault_name(self) -> str | None:
        return None


@pytest.mark.asyncio
async def test_real_indexer_markdown_strategy_produces_section_metadata(
    migrated: asyncpg.Pool,
    admin_dsn: str,
    pg_container: str,
) -> None:
    """End-to-end : workspace configuré en markdown → chunks ont la metadata."""
    req = WorkspaceCreateRequest(
        name="ws_md_e2e",
        indexer=IndexerSpec(
            provider="ollama",
            model="mxbai-embed-large",
            api_key_ref=None,
            base_url="http://stub:11434",
        ),
    )
    ws = await create_workspace(
        request=req,
        config_pool=migrated,
        admin_dsn=admin_dsn,
        resolver=_NullResolver(),  # type: ignore[arg-type]
        default_vault_name="rag",
        api_key_dek=_TEST_DEK,
    )
    rag_base = await migrated.fetchval(
        "SELECT rag_base FROM workspaces WHERE id = $1",
        ws["id"],
    )
    ws_dsn = derive_workspace_dsn(admin_dsn, rag_base)

    registry: WorkspacePoolRegistry | None = None
    try:
        # Reconfigure le workspace en markdown.
        await migrated.execute(
            "UPDATE chunking_configs SET strategy=$1, extras=$2::jsonb WHERE workspace_id = $3",
            "markdown",
            json.dumps({"heading_levels": [1, 2]}),
            ws["id"],
        )

        # Recrée embeddings avec dim=8 pour matcher le stub.
        # create_workspace l'a créée avec dim=1024 (mxbai-embed-large) ; le stub
        # renvoie des vecteurs 8-dim. Shortcut volontaire de la cohérence dim
        # modèle ↔ table (pas de chemin de prod ici).
        conn = await asyncpg.connect(ws_dsn)
        try:
            await conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
            await conn.execute(
                "CREATE TABLE embeddings ("
                "id SERIAL PRIMARY KEY, path TEXT NOT NULL, "
                "chunk_index INT NOT NULL, content TEXT NOT NULL, "
                "embedding vector(8) NOT NULL, "
                "metadata JSONB NOT NULL DEFAULT '{}'::jsonb, "
                "indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(), "
                "UNIQUE (path, chunk_index))"
            )
        finally:
            await conn.close()

        registry = WorkspacePoolRegistry(
            config_dsn=pg_container,
            admin_dsn=admin_dsn,
        )
        await registry.start()

        indexer = RealIndexer(
            config_pool=migrated,
            pool_registry=registry,
            secret_resolver=_NullResolver(),  # type: ignore[arg-type]
            client_provider=_StubClientProvider(),  # type: ignore[arg-type]
            provider_factory=lambda **_kw: _StubProvider(),
        )

        nb = await indexer.index_file(
            workspace_id=ws["id"],
            path="README.md",
            content=README_DEMO,
            content_hash="sha256:demo",
            indexer_used="ollama/mxbai-embed-large",
        )
        # Au moins 4 sections : préambule + Installation + Usage + Reference.
        assert nb >= 4

        # Vérifier la metadata stockée.
        conn = await asyncpg.connect(ws_dsn)
        try:
            rows = await conn.fetch(
                "SELECT chunk_index, content, metadata FROM embeddings "
                "WHERE path = 'README.md' ORDER BY chunk_index",
            )
        finally:
            await conn.close()

        for row in rows:
            meta_raw = row["metadata"]
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            assert set(meta.keys()) == {
                "section_title",
                "section_path",
                "heading_level",
            }

        # Au moins un chunk a heading_level=1.
        levels = []
        for row in rows:
            meta_raw = row["metadata"]
            meta = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
            levels.append(meta["heading_level"])
        assert 1 in levels
    finally:
        if registry is not None:
            await registry.close_all()
        await drop_workspace_database(admin_dsn, rag_base)
        await migrated.execute(
            "DELETE FROM workspaces WHERE id = $1",
            ws["id"],
        )
