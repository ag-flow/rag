from __future__ import annotations

from pathlib import Path

import asyncpg
import pytest

from rag.db.migrations import run_migrations
from tests.integration._workspace_seed import seed_workspace

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

OWNER = "6" * 64


async def _insert_template(
    conn: asyncpg.Connection, *, name: str, target: str, timing: str
) -> object:
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
async def test_target_timing_combos_enforced(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        # combos supportés
        await _insert_template(
            conn, name="ctx-chunk-061", target="chunk", timing="embedding_inline"
        )
        await _insert_template(
            conn,
            name="ctx-mermaid-061",
            target="region:code_fence:mermaid",
            timing="embedding_inline",
        )
        version = await conn.fetchval(
            "SELECT prompt_version FROM prompt_templates WHERE name='ctx-chunk-061'"
        )
        assert version == 1
        # combos refusés par le CHECK
        with pytest.raises(asyncpg.CheckViolationError):
            await _insert_template(
                conn, name="bad-combo-1", target="chunk", timing="post_index_metadata"
            )
        with pytest.raises(asyncpg.CheckViolationError):
            await _insert_template(
                conn, name="bad-combo-2", target="document", timing="embedding_inline"
            )


@pytest.mark.asyncio
async def test_context_cache_pk_and_cascade(session_pool: asyncpg.Pool) -> None:
    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        template_id = await _insert_template(
            conn, name="ctx-cache-061", target="chunk", timing="embedding_inline"
        )
        ws_id = await seed_workspace(conn, name="ws-ctx-061")
        await conn.execute(
            "INSERT INTO chunk_context_cache "
            "(workspace_id, source_hash, template_id, prompt_version, context, "
            " llm_provider, llm_model) "
            "VALUES ($1, 'h1', $2, 1, 'ctx', 'claude', 'haiku')",
            ws_id,
            template_id,
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO chunk_context_cache "
                "(workspace_id, source_hash, template_id, prompt_version, context, "
                " llm_provider, llm_model) "
                "VALUES ($1, 'h1', $2, 1, 'ctx2', 'claude', 'haiku')",
                ws_id,
                template_id,
            )
        # version différente = nouvelle entrée (invalidation par prompt_version)
        await conn.execute(
            "INSERT INTO chunk_context_cache "
            "(workspace_id, source_hash, template_id, prompt_version, context, "
            " llm_provider, llm_model) "
            "VALUES ($1, 'h1', $2, 2, 'ctx-v2', 'claude', 'haiku')",
            ws_id,
            template_id,
        )
        await conn.execute("DELETE FROM prompt_templates WHERE id=$1", template_id)
        remaining = await conn.fetchval(
            "SELECT count(*) FROM chunk_context_cache WHERE template_id=$1", template_id
        )
        assert remaining == 0  # CASCADE template
        await conn.execute("DELETE FROM workspaces WHERE id=$1", ws_id)


@pytest.mark.asyncio
async def test_prompt_edit_bumps_version(session_pool: asyncpg.Pool) -> None:
    """Le bump de prompt_version invalide le cache (clé composite)."""
    from rag.schemas.enrichments import PromptTemplatePatch
    from rag.services.prompt_templates import patch_prompt_template

    await run_migrations(session_pool, MIGRATIONS_DIR)
    async with session_pool.acquire() as conn:
        template_id = await _insert_template(
            conn, name="ctx-bump-061", target="chunk", timing="embedding_inline"
        )
        unchanged = await patch_prompt_template(
            conn,
            owner_id=OWNER,
            template_id=str(template_id),
            req=PromptTemplatePatch(description="juste la description"),
        )
        assert unchanged.prompt_version == 1
        bumped = await patch_prompt_template(
            conn,
            owner_id=OWNER,
            template_id=str(template_id),
            req=PromptTemplatePatch(prompt="Situe très précisément {chunk}"),
        )
        assert bumped.prompt_version == 2
