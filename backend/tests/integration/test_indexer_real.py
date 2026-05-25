from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import asyncpg
import pytest
import pytest_asyncio

from rag.db.migrations import run_migrations
from rag.db.pool import WorkspacePoolRegistry
from rag.indexer.providers.protocol import (
    EmbeddingAuthError,
    EmbeddingProvider,
)
from rag.indexer.real import RealIndexer
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


class _StubProvider:
    """Provider mocké : retourne des vecteurs déterministes (dim 4)."""

    def __init__(self, *, raise_on_call: Exception | None = None) -> None:
        self._raise = raise_on_call
        self.calls: list[list[str]] = []

    async def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if self._raise is not None:
            raise self._raise
        self.calls.append(texts)
        return [[float(i + 1), 0.0, 0.0, 0.0] for i in range(len(texts))]


class _StubResolver:
    async def resolve_with_retry(self, ref: str) -> str:
        return "tok-stub"


class _StubClientProvider:
    """Fournit un default vault name fixe ('rag') pour les tests."""

    async def get_default_vault_name(self) -> str | None:
        return "rag"


@pytest_asyncio.fixture
async def real_indexer_setup(
    pg_container: str,
    session_pool: asyncpg.Pool,
) -> AsyncIterator[dict[str, Any]]:
    """Provisionne :
    - migrations 001-007 sur la base config
    - 1 workspace 'ws_real_a' avec provider 'openai' / model 'text-embedding-3-small'
    - 1 base workspace `rag_test_emb_<uuid>` avec table embeddings (dim 4 pour les tests)
    - WorkspacePoolRegistry initialisé
    """
    await run_migrations(session_pool, MIGRATIONS_DIR)

    admin_dsn = pg_container.rsplit("/", 1)[0] + "/postgres"

    # Crée la base workspace test
    ws_dbname = f"rag_test_emb_{uuid.uuid4().hex[:10]}"
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'CREATE DATABASE "{ws_dbname}"')
    finally:
        await admin.close()
    ws_dsn = pg_container.rsplit("/", 1)[0] + f"/{ws_dbname}"
    ws_setup = await asyncpg.connect(ws_dsn)
    try:
        await ws_setup.execute("CREATE EXTENSION IF NOT EXISTS vector")
        await ws_setup.execute(
            """
            CREATE TABLE embeddings (
                id SERIAL PRIMARY KEY,
                path TEXT NOT NULL,
                chunk_index INT NOT NULL,
                content TEXT NOT NULL,
                embedding vector(4) NOT NULL,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                indexed_at TIMESTAMPTZ NOT NULL DEFAULT now(),
                UNIQUE (path, chunk_index)
            )
            """
        )
    finally:
        await ws_setup.close()

    # Crée le workspace en config DB
    async with session_pool.acquire() as conn:
        ws_id = await seed_workspace(
            conn,
            name="ws_real_a",
            rag_cnx=ws_dsn,
            rag_base=ws_dbname,
        )
        await conn.execute(
            "INSERT INTO indexer_configs (workspace_id, provider, model, api_key_ref, dimension) "
            "VALUES ($1, 'openai', 'text-embedding-3-small', 'openai_key', 4)",
            ws_id,
        )
        # M9 : chunking_configs est requis pour RealIndexer (JOIN dans
        # _load_workspace_context). On utilise les défauts du plan.
        await conn.execute(
            "INSERT INTO chunking_configs "
            "(workspace_id, strategy, max_chars, min_chars, overlap_chars, extras) "
            "VALUES ($1, 'paragraph', 2000, 200, 200, '{}'::jsonb)",
            ws_id,
        )

    # Registry pour les pools workspace
    registry = WorkspacePoolRegistry(
        config_dsn=pg_container,
        admin_dsn=admin_dsn,
    )
    await registry.start()

    yield {
        "workspace_id": ws_id,
        "workspace_name": "ws_real_a",
        "ws_dsn": ws_dsn,
        "ws_dbname": ws_dbname,
        "registry": registry,
    }

    await registry.close_all()

    # Cleanup base workspace
    admin = await asyncpg.connect(admin_dsn)
    try:
        await admin.execute(f'DROP DATABASE IF EXISTS "{ws_dbname}" WITH (FORCE)')
    finally:
        await admin.close()


def _factory_with_stub(stub: _StubProvider) -> Any:
    def _factory(**_kwargs: Any) -> EmbeddingProvider:
        return stub

    return _factory


@pytest.mark.asyncio
async def test_real_indexer_index_file_inserts_chunks_and_indexed_documents(
    session_pool: asyncpg.Pool,
    real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    stub = _StubProvider()
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(stub),
    )

    chunks_count = await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="docs/a.md",
        content="Hello world.\n\nSecond paragraph.",
        content_hash="sha256:abc",
        indexer_used="openai/text-embedding-3-small",
    )

    assert chunks_count >= 1
    assert len(stub.calls) == 1  # 1 batch d'embeddings

    # Vérifie indexed_documents
    row = await session_pool.fetchrow(
        "SELECT content_hash, indexer_used FROM indexed_documents "
        "WHERE workspace_id=$1 AND path='docs/a.md'",
        setup["workspace_id"],
    )
    assert row is not None
    assert row["content_hash"] == "sha256:abc"

    # Vérifie embeddings dans rag_test_emb_<uuid>
    ws_pool = await setup["registry"].get_workspace_pool(
        setup["workspace_name"],
        setup["ws_dsn"],
    )
    chunks_in_db = await ws_pool.fetch(
        "SELECT chunk_index FROM embeddings WHERE path='docs/a.md' ORDER BY chunk_index"
    )
    assert len(chunks_in_db) == chunks_count


@pytest.mark.asyncio
async def test_real_indexer_index_file_replaces_old_chunks(
    session_pool: asyncpg.Pool,
    real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(_StubProvider()),
    )
    # Index v1
    await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="docs/a.md",
        content="v1 content here.",
        content_hash="h1",
        indexer_used="openai/text-embedding-3-small",
    )
    # Index v2 (contenu différent → nouvelle indexation)
    await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="docs/a.md",
        content="v2 brand new content.",
        content_hash="h2",
        indexer_used="openai/text-embedding-3-small",
    )

    # Le hash en base reflète v2
    h = await session_pool.fetchval(
        "SELECT content_hash FROM indexed_documents WHERE path='docs/a.md'",
    )
    assert h == "h2"


@pytest.mark.asyncio
async def test_real_indexer_index_file_empty_content_returns_zero(
    session_pool: asyncpg.Pool,
    real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    stub = _StubProvider()
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(stub),
    )
    n = await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="empty.md",
        content="",
        content_hash="h0",
        indexer_used="openai/text-embedding-3-small",
    )
    assert n == 0
    assert stub.calls == []  # pas d'appel provider

    # indexed_documents : pas de ligne (rien à indexer)
    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE path='empty.md'",
    )
    assert row is None


@pytest.mark.asyncio
async def test_real_indexer_delete_file_removes_chunks_and_metadata(
    session_pool: asyncpg.Pool,
    real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(_StubProvider()),
    )
    await indexer.index_file(
        workspace_id=setup["workspace_id"],
        path="docs/b.md",
        content="some content",
        content_hash="h",
        indexer_used="openai/text-embedding-3-small",
    )
    await indexer.delete_file(
        workspace_id=setup["workspace_id"],
        path="docs/b.md",
    )

    # indexed_documents : ligne supprimée
    row = await session_pool.fetchrow(
        "SELECT 1 FROM indexed_documents WHERE path='docs/b.md'",
    )
    assert row is None

    # embeddings : aussi supprimés
    ws_pool = await setup["registry"].get_workspace_pool(
        setup["workspace_name"],
        setup["ws_dsn"],
    )
    rows = await ws_pool.fetch(
        "SELECT 1 FROM embeddings WHERE path='docs/b.md'",
    )
    assert rows == []


@pytest.mark.asyncio
async def test_real_indexer_provider_auth_error_propagates(
    session_pool: asyncpg.Pool,
    real_indexer_setup: dict[str, Any],
) -> None:
    setup = real_indexer_setup
    bad_stub = _StubProvider(raise_on_call=EmbeddingAuthError("401"))
    indexer = RealIndexer(
        config_pool=session_pool,
        pool_registry=setup["registry"],
        secret_resolver=_StubResolver(),  # type: ignore[arg-type]
        client_provider=_StubClientProvider(),  # type: ignore[arg-type]
        provider_factory=_factory_with_stub(bad_stub),
    )
    with pytest.raises(EmbeddingAuthError):
        await indexer.index_file(
            workspace_id=setup["workspace_id"],
            path="docs/x.md",
            content="hello",
            content_hash="h",
            indexer_used="openai/text-embedding-3-small",
        )
