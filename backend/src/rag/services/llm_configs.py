from __future__ import annotations

from typing import Any

import asyncpg
import structlog

from rag.schemas.playground import LlmConfigCreate, LlmConfigOut, LlmConfigPatch

log = structlog.get_logger(__name__)


async def list_llm_configs(
    conn: asyncpg.Connection, *, workspace_name: str
) -> list[LlmConfigOut]:
    rows = await conn.fetch(
        """
        SELECT lc.id, lc.provider, lc.model, lc.base_url, lc.api_key_ref,
               lc.enabled, lc.created_at
        FROM workspace_llm_configs lc
        JOIN workspaces w ON w.id = lc.workspace_id
        WHERE w.name = $1
        ORDER BY lc.provider, lc.model
        """,
        workspace_name,
    )
    return [LlmConfigOut.model_validate(dict(r)) for r in rows]


async def create_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    req: LlmConfigCreate,
) -> LlmConfigOut:
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_llm_configs
            (workspace_id, provider, model, base_url, api_key_ref, enabled)
        SELECT w.id, $2, $3, $4, $5, $6
        FROM workspaces w WHERE w.name = $1
        RETURNING id, provider, model, base_url, api_key_ref, enabled, created_at
        """,
        workspace_name,
        req.provider,
        req.model,
        req.base_url,
        req.api_key_ref,
        req.enabled,
    )
    if row is None:
        raise ValueError(f"workspace {workspace_name!r} not found")
    log.info("llm_config.created", workspace=workspace_name, provider=req.provider, model=req.model)
    return LlmConfigOut.model_validate(dict(row))


async def patch_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    config_id: str,
    req: LlmConfigPatch,
) -> LlmConfigOut | None:
    row = await conn.fetchrow(
        """
        UPDATE workspace_llm_configs lc
        SET enabled = $3
        FROM workspaces w
        WHERE w.id = lc.workspace_id AND w.name = $1 AND lc.id = $2::uuid
        RETURNING lc.id, lc.provider, lc.model, lc.base_url,
                  lc.api_key_ref, lc.enabled, lc.created_at
        """,
        workspace_name,
        config_id,
        req.enabled,
    )
    return LlmConfigOut.model_validate(dict(row)) if row else None


async def delete_llm_config(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    config_id: str,
) -> bool:
    result = await conn.execute(
        """
        DELETE FROM workspace_llm_configs lc
        USING workspaces w
        WHERE w.id = lc.workspace_id AND w.name = $1 AND lc.id = $2::uuid
        """,
        workspace_name,
        config_id,
    )
    return result != "DELETE 0"


async def get_llm_config_for_chat(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    provider: str,
    model: str,
) -> dict[str, Any] | None:
    """Retourne la config LLM enabled pour (workspace, provider, model)."""
    row = await conn.fetchrow(
        """
        SELECT lc.provider, lc.model, lc.base_url, lc.api_key_ref
        FROM workspace_llm_configs lc
        JOIN workspaces w ON w.id = lc.workspace_id
        WHERE w.name = $1 AND lc.provider = $2 AND lc.model = $3 AND lc.enabled = true
        """,
        workspace_name,
        provider,
        model,
    )
    return dict(row) if row else None
