from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from rag.schemas.chunking_strategies import StrategyCreate, StrategyPromptSpec
from rag.services import chunking_strategies as svc

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER = "9" * 64


async def _template(conn: asyncpg.Connection, name: str, *, target: str, timing: str) -> object:
    return await conn.fetchval(
        "INSERT INTO prompt_templates "
        "(owner_id, name, language, metadata_key, prompt, target, timing) "
        "VALUES ($1, $2, 'markdown', $2, 'Situe {chunk}', $3, $4) RETURNING id",
        OWNER,
        name,
        target,
        timing,
    )


@pytest.mark.asyncio
async def test_strategy_prompts_roundtrip_guards_and_duplicate(
    session_pool: asyncpg.Pool,
) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    conn = await session_pool.acquire()
    try:
        chunk_tpl = await _template(conn, "sp-chunk-062", target="chunk", timing="embedding_inline")
        region_tpl = await _template(
            conn, "sp-region-062", target="region:code_fence:mermaid", timing="embedding_inline"
        )
        doc_tpl = await _template(
            conn, "sp-doc-062", target="document", timing="post_index_metadata"
        )

        no_parser = await svc.create_strategy(
            conn, owner_id=OWNER, req=StrategyCreate(label="SP sans parser", algo="prose")
        )
        with_parser = await svc.create_strategy(
            conn,
            owner_id=OWNER,
            req=StrategyCreate(label="SP avec parser", algo="prose", parser_slug="markdown"),
        )

        # Garde timing : un template post_index_metadata ne se lie pas.
        with pytest.raises(svc.InvalidStrategyError):
            await svc.set_strategy_prompts(
                conn,
                owner_id=OWNER,
                strategy_id=no_parser.id,
                prompts=[StrategyPromptSpec(template_id=doc_tpl)],
            )
        # Garde parser : region:* exige parser_slug (S6.1).
        with pytest.raises(svc.InvalidStrategyError):
            await svc.set_strategy_prompts(
                conn,
                owner_id=OWNER,
                strategy_id=no_parser.id,
                prompts=[StrategyPromptSpec(template_id=region_tpl)],
            )

        saved = await svc.set_strategy_prompts(
            conn,
            owner_id=OWNER,
            strategy_id=with_parser.id,
            prompts=[
                StrategyPromptSpec(template_id=chunk_tpl, order_index=1),
                StrategyPromptSpec(template_id=region_tpl, order_index=2),
            ],
        )
        assert [p.template_name for p in saved] == ["sp-chunk-062", "sp-region-062"]

        detail = await svc.get_strategy(conn, owner_id=OWNER, strategy_id=with_parser.id)
        assert len(detail.prompts) == 2

        # Duplication : les prompts voyagent avec la stratégie.
        copy = await svc.duplicate_strategy(
            conn, owner_id=OWNER, source_id=with_parser.id, label="SP copie"
        )
        assert len(copy.prompts) == 2

        # RESTRICT : template lié → suppression refusée côté DB.
        with pytest.raises(asyncpg.ForeignKeyViolationError):
            await conn.execute("DELETE FROM prompt_templates WHERE id=$1", chunk_tpl)
    finally:
        await session_pool.release(conn)
