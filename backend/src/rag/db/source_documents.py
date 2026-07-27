"""Table workspace `source_documents` — contenu brut des documents poussés.

Source de vérité du re-chunk pour les documents sans source git (push docflow,
API REST) : upsert au push, delete à la suppression, lecture par le job de
réindexation (migration workspace 006, fiche bug aced5d5e).
"""

from __future__ import annotations

import asyncpg


async def upsert_source_document(
    pool: asyncpg.Pool,
    *,
    path: str,
    content: str,
    content_hash: str,
    title: str | None,
    source_url: str | None,
) -> None:
    await pool.execute(
        """
        INSERT INTO source_documents (path, content, content_hash, title, source_url, pushed_at)
        VALUES ($1, $2, $3, $4, $5, now())
        ON CONFLICT (path) DO UPDATE
        SET content      = EXCLUDED.content,
            content_hash = EXCLUDED.content_hash,
            title        = EXCLUDED.title,
            source_url   = COALESCE(EXCLUDED.source_url, source_documents.source_url),
            pushed_at    = EXCLUDED.pushed_at
        """,
        path,
        content,
        content_hash,
        title,
        source_url,
    )


async def delete_source_document(pool: asyncpg.Pool, path: str) -> None:
    await pool.execute("DELETE FROM source_documents WHERE path = $1", path)


async def list_source_documents(pool: asyncpg.Pool) -> list[asyncpg.Record]:
    """Tous les documents stockés, en ordre stable (path). Colonnes :
    path, content, content_hash, title, source_url."""
    return await pool.fetch(
        "SELECT path, content, content_hash, title, source_url FROM source_documents ORDER BY path"
    )
