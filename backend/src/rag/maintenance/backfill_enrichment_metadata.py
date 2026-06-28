"""Backfill one-shot : ajouter enrichment_key + source_path dans la metadata
des chunks d'enrichissement existants (antérieurs à M17).

Exécution : uv run python -m rag.maintenance.backfill_enrichment_metadata

Idempotent : ignore les chunks qui ont déjà enrichment_key dans metadata.
Pilote par document_enrichments (source de vérité), pas par parsing de '::'.
"""
from __future__ import annotations

import asyncio
import json
import os

import asyncpg
import structlog

log = structlog.get_logger(__name__)


async def _backfill_workspace(ws_pool: asyncpg.Pool, ws_enrichments: list[dict]) -> int:
    """Met à jour les chunks d'une workspace. Retourne le nb de chunks updatés."""
    updated = 0
    for row in ws_enrichments:
        path = row["path"]            # path synthétique: src/a.py::public_functions
        metadata_key = row["metadata_key"]
        source_path = path.rsplit("::", 1)[0] if "::" in path else path
        extra = json.dumps({"enrichment_key": metadata_key, "source_path": source_path})

        count = await ws_pool.fetchval(
            """
            WITH updated AS (
                UPDATE embeddings
                SET metadata = ($1::jsonb || metadata)
                WHERE path = $2
                  AND NOT (metadata ? 'enrichment_key')
                RETURNING 1
            )
            SELECT count(*) FROM updated
            """,
            extra,
            path,
        )
        if count and count > 0:
            updated += int(count)
            log.info("backfill.chunks_updated", path=path, metadata_key=metadata_key, count=count)
    return updated


async def run_backfill(
    config_dsn: str,
    workspace_dsn_map: dict[str, str] | None = None,
) -> int:
    """Backfill principal. workspace_dsn_map = {workspace_name: rag_cnx} optionnel.

    Si absent, interroge workspaces pour obtenir les rag_cnx.
    Retourne le total de chunks mis à jour.
    """
    config_pool = await asyncpg.create_pool(config_dsn)
    total = 0
    ws_pool_cache: dict[str, asyncpg.Pool] = {}

    try:
        rows = await config_pool.fetch(
            """
            SELECT de.workspace_id, de.path, de.metadata_key, w.rag_cnx, w.name
            FROM document_enrichments de
            JOIN workspaces w ON w.id = de.workspace_id
            ORDER BY w.name
            """
        )
        # Grouper par rag_cnx (workspace pool)
        by_rag: dict[str, list[dict]] = {}
        for row in rows:
            rag_cnx = row["rag_cnx"]
            by_rag.setdefault(rag_cnx, []).append(dict(row))

        for rag_cnx, ws_rows in by_rag.items():
            if rag_cnx not in ws_pool_cache:
                ws_pool_cache[rag_cnx] = await asyncpg.create_pool(rag_cnx)
            ws_pool = ws_pool_cache[rag_cnx]
            n = await _backfill_workspace(ws_pool, ws_rows)
            total += n

    finally:
        await config_pool.close()
        for p in ws_pool_cache.values():
            await p.close()

    return total


async def main() -> None:
    dsn = os.environ.get("DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("DATABASE_URL requis")
    total = await run_backfill(dsn)
    log.info("backfill.done", total_chunks_updated=total)


if __name__ == "__main__":
    asyncio.run(main())
