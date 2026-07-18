from __future__ import annotations

from typing import Protocol

import asyncpg
import structlog

from rag.db.workspace_search import _ChildHit, lexical_search

log = structlog.get_logger(__name__)

LEXICAL_ENGINES: tuple[str, ...] = ("fts", "bm25")


class LexicalEngineProtocol(Protocol):
    """Contrat de moteur lexical (D5, SR4.1) : indexer, chercher, des rangs.

    Les scores ne sont JAMAIS comparés entre moteurs ni au canal vectoriel —
    la fusion RRF ne consomme que les rangs (D6).
    """

    slug: str

    async def is_available(self, conn: asyncpg.Connection) -> bool: ...

    async def ensure_index(self, conn: asyncpg.Connection) -> None:
        """Reconstruit l'index du moteur (bascule D5) et retire celui de
        l'autre moteur. Jamais de ré-embedding."""
        ...

    async def search(
        self, workspace_pool: asyncpg.Pool, *, query: str, top_k_fetch: int
    ) -> list[_ChildHit]: ...


class FtsEngine:
    """FTS natif Postgres — implémentation par défaut (D5).

    S'appuie sur la colonne générée bilingue pondérée `content_tsv`
    (workspace migration 005) : l'index vit dans le schéma, ensure_index ne
    fait que garantir le GIN et retirer l'index BM25 éventuel.
    """

    slug = "fts"

    async def is_available(self, conn: asyncpg.Connection) -> bool:
        return True  # natif — toujours disponible

    async def ensure_index(self, conn: asyncpg.Connection) -> None:
        await conn.execute("DROP INDEX IF EXISTS embeddings_bm25")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS embeddings_content_tsv "
            "ON embeddings USING GIN (content_tsv)"
        )

    async def search(
        self, workspace_pool: asyncpg.Pool, *, query: str, top_k_fetch: int
    ) -> list[_ChildHit]:
        return await lexical_search(workspace_pool, query=query, top_k_fetch=top_k_fetch)


class Bm25Engine:
    """Vrai BM25 via l'extension pg_search (ParadeDB) — activable (D5).

    Ce que le BM25 apporte vs FTS : IDF global (les termes rares pèsent
    plus), saturation de fréquence (10 occurrences ne valent pas 10 fois le score),
    normalisation par longueur. Utile sur les gros corpus hétérogènes ;
    le FTS bilingue suffit à la plupart des usages.
    """

    slug = "bm25"

    async def is_available(self, conn: asyncpg.Connection) -> bool:
        return bool(
            await conn.fetchval("SELECT 1 FROM pg_available_extensions WHERE name = 'pg_search'")
        )

    async def ensure_index(self, conn: asyncpg.Connection) -> None:
        await conn.execute("CREATE EXTENSION IF NOT EXISTS pg_search")
        await conn.execute("DROP INDEX IF EXISTS embeddings_content_tsv")
        await conn.execute(
            "CREATE INDEX IF NOT EXISTS embeddings_bm25 ON embeddings "
            "USING bm25 (id, content) WITH (key_field='id')"
        )

    async def search(
        self, workspace_pool: asyncpg.Pool, *, query: str, top_k_fetch: int
    ) -> list[_ChildHit]:
        from rag.db.workspace_search import _parse_metadata

        async with workspace_pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT e.path, e.chunk_index, e.chunk_hash, e.section_id,
                       COALESCE(s.content, e.content) AS content,
                       paradedb.score(e.id) AS lexical_score,
                       e.metadata
                FROM embeddings e
                LEFT JOIN sections s ON s.id = e.section_id
                WHERE e.content @@@ $1
                ORDER BY lexical_score DESC
                LIMIT $2
                """,
                query,
                top_k_fetch,
            )
        return [
            _ChildHit(
                path=r["path"],
                chunk_index=r["chunk_index"],
                chunk_hash=r["chunk_hash"],
                section_id=r["section_id"],
                content=r["content"],
                score=float(r["lexical_score"]),
                metadata=_parse_metadata(r["metadata"]),
            )
            for r in rows
        ]


_ENGINES: dict[str, LexicalEngineProtocol] = {"fts": FtsEngine(), "bm25": Bm25Engine()}


def get_lexical_engine(slug: str) -> LexicalEngineProtocol:
    engine = _ENGINES.get(slug)
    if engine is None:
        raise ValueError(f"unknown lexical engine: {slug!r}")
    return engine
