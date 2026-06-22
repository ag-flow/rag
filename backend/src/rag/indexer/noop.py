from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog

log = structlog.get_logger(__name__)


class NoOpIndexer:
    """Implémentation M3 de `IndexerProtocol` : maintient seulement
    `indexed_documents` (hash + indexer_used), NE touche PAS à pgvector.

    Remplacé en M4 par un indexer qui ajoute chunking + embeddings +
    upsert pgvector.
    """

    def __init__(self, config_pool: asyncpg.Pool) -> None:
        self._config_pool = config_pool

    async def index_file(
        self,
        *,
        workspace_id: UUID,
        path: str,
        content: str,
        content_hash: str,
        indexer_used: str,
        strategy_override: str | None = None,
    ) -> int:
        """INSERT/UPDATE `indexed_documents` via ON CONFLICT. Retourne 1
        (1 chunk fictif). `content` et `strategy_override` ignorés en M3.
        """
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO indexed_documents
                    (workspace_id, path, content_hash, indexer_used, indexed_at)
                VALUES ($1, $2, $3, $4, now())
                ON CONFLICT (workspace_id, path) DO UPDATE
                SET content_hash = EXCLUDED.content_hash,
                    indexer_used = EXCLUDED.indexer_used,
                    indexed_at   = EXCLUDED.indexed_at
                """,
                workspace_id,
                path,
                content_hash,
                indexer_used,
            )
        log.info(
            "noop_indexer.index_file",
            workspace_id=str(workspace_id),
            path=path,
            content_len=len(content),
        )
        return 1

    async def delete_file(self, *, workspace_id: UUID, path: str) -> None:
        """DELETE indexed_documents. Idempotent (silencieux si absent)."""
        async with self._config_pool.acquire() as conn:
            await conn.execute(
                "DELETE FROM indexed_documents WHERE workspace_id=$1 AND path=$2",
                workspace_id,
                path,
            )
        log.info(
            "noop_indexer.delete_file",
            workspace_id=str(workspace_id),
            path=path,
        )
