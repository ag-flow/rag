from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.workspace_migrations.runner import apply_pending
from rag.db.workspace_schema import create_embeddings_table
from rag.db.workspace_search import lexical_search

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# Tokens RÉELS du corpus — critère d'acceptation SR2.1 (D4 règle 3).
_ROWS = [
    "La table chunking_strategy_region_routes porte les routes de régions.",
    "Le RoutingChunker applique la migration 040 aux stratégies nommées.",
    "Chemin backend/src/rag/indexer/real.py — pipeline structured.",
    "Les stratégies de découpage sont possédées par leurs utilisateurs.",
]


async def _seed(ws_dsn: str) -> asyncpg.Pool:
    await create_embeddings_table(ws_dsn, dimension=3)
    await apply_pending(ws_dsn)
    pool = await asyncpg.create_pool(ws_dsn, min_size=1, max_size=2)
    async with pool.acquire() as conn:
        for i, content in enumerate(_ROWS):
            await conn.execute(
                "INSERT INTO embeddings (path, chunk_index, content, embedding) "
                "VALUES ($1, $2, $3, '[0,0,0]'::vector)",
                f"doc{i}.md",
                0,
                content,
            )
    return pool


@pytest.mark.asyncio
async def test_tokenisation_reelle_et_symetrie(workspace_test_db: tuple[str, str]) -> None:
    _, ws_dsn = workspace_test_db
    pool = await _seed(ws_dsn)
    try:
        # Identifiant technique exact (canal simple, poids A)
        hits = await lexical_search(pool, query="chunking_strategy_region_routes", top_k_fetch=10)
        assert [h.path for h in hits][:1] == ["doc0.md"]

        # Numéro nu « 040 »
        hits = await lexical_search(pool, query="040", top_k_fetch=10)
        assert any(h.path == "doc1.md" for h in hits)

        # camelCase exact
        hits = await lexical_search(pool, query="RoutingChunker", top_k_fetch=10)
        assert any(h.path == "doc1.md" for h in hits)

        # Racine française : « stratégie » (singulier) matche « stratégies »
        hits = await lexical_search(pool, query="stratégie", top_k_fetch=10)
        assert any(h.path == "doc3.md" for h in hits)

        # Saisie SANS accents : « strategie » matche aussi (simple+unaccent)
        hits = await lexical_search(pool, query="strategie de decoupage", top_k_fetch=10)
        assert any(h.path == "doc3.md" for h in hits)

        # Hiérarchie D4 : le match exact (A) domine le match par racine (B)
        hits = await lexical_search(pool, query="stratégies", top_k_fetch=10)
        assert hits[0].path in ("doc1.md", "doc3.md")
    finally:
        await pool.close()
