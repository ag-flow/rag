from __future__ import annotations

import asyncpg
import structlog

from rag.schemas.enrichments import (
    TriggerCreate,
    TriggerOut,
    TriggerPatch,
    TriggerPromptCreate,
    TriggerPromptOut,
    TriggerPromptPatch,
)

log = structlog.get_logger(__name__)


class UnknownTriggerStrategyError(ValueError):
    """Stratégie invisible pour ce caller (ni système ni la sienne)."""


async def _check_strategy_visible(
    conn: asyncpg.Connection, *, strategy_id: object, owner_id: str
) -> None:
    """Le binding est par id (spec chunking §5) mais s'écrit uniquement vers
    une stratégie visible du caller : système ou sa bibliothèque."""
    visible = await conn.fetchval(
        "SELECT 1 FROM chunking_strategies s "
        "WHERE s.id = $1 AND s.workspace_id IS NULL "
        "AND (s.owner_id IS NULL OR s.owner_id = $2)",
        strategy_id,
        owner_id,
    )
    if visible is None:
        raise UnknownTriggerStrategyError(f"stratégie introuvable : {strategy_id}")


async def list_triggers(
    conn: asyncpg.Connection, *, workspace_name: str
) -> list[TriggerOut]:
    rows = await conn.fetch(
        """
        SELECT t.id, t.extension, t.enabled, t.strategy_id, t.created_at
        FROM workspace_extension_triggers t
        JOIN workspaces w ON w.id = t.workspace_id
        WHERE w.name = $1
        ORDER BY t.extension
        """,
        workspace_name,
    )
    return [TriggerOut.model_validate(dict(r)) for r in rows]


async def create_trigger(
    conn: asyncpg.Connection, *, workspace_name: str, req: TriggerCreate, owner_id: str
) -> TriggerOut:
    if req.strategy_id is not None:
        await _check_strategy_visible(conn, strategy_id=req.strategy_id, owner_id=owner_id)
    row = await conn.fetchrow(
        """
        INSERT INTO workspace_extension_triggers (workspace_id, extension, enabled, strategy_id)
        SELECT w.id, $2, $3, $4 FROM workspaces w WHERE w.name = $1
        RETURNING id, extension, enabled, strategy_id, created_at
        """,
        workspace_name, req.extension, req.enabled, req.strategy_id,
    )
    if row is None:
        raise ValueError(f"workspace {workspace_name!r} not found")
    log.info("trigger.created", workspace=workspace_name, extension=req.extension)
    return TriggerOut.model_validate(dict(row))


async def patch_trigger(
    conn: asyncpg.Connection,
    *,
    workspace_name: str,
    trigger_id: str,
    req: TriggerPatch,
    owner_id: str,
) -> TriggerOut | None:
    async with conn.transaction():
        current = await conn.fetchrow(
            """
            SELECT t.enabled, t.strategy_id
            FROM workspace_extension_triggers t
            JOIN workspaces w ON w.id = t.workspace_id
            WHERE w.name = $1 AND t.id = $2::uuid
            FOR UPDATE OF t
            """,
            workspace_name, trigger_id,
        )
        if current is None:
            return None
        enabled = req.enabled if req.enabled is not None else current["enabled"]
        strategy_id = (
            req.strategy_id if "strategy_id" in req.model_fields_set else current["strategy_id"]
        )
        if strategy_id is not None and strategy_id != current["strategy_id"]:
            await _check_strategy_visible(conn, strategy_id=strategy_id, owner_id=owner_id)
        row = await conn.fetchrow(
            """
            UPDATE workspace_extension_triggers t SET enabled = $3, strategy_id = $4
            FROM workspaces w
            WHERE w.id = t.workspace_id AND w.name = $1 AND t.id = $2::uuid
            RETURNING t.id, t.extension, t.enabled, t.strategy_id, t.created_at
            """,
            workspace_name, trigger_id, enabled, strategy_id,
        )
    return TriggerOut.model_validate(dict(row)) if row else None


async def delete_trigger(
    conn: asyncpg.Connection, *, workspace_name: str, trigger_id: str
) -> bool:
    result = await conn.execute(
        """
        DELETE FROM workspace_extension_triggers t
        USING workspaces w
        WHERE w.id = t.workspace_id AND w.name = $1 AND t.id = $2::uuid
        """,
        workspace_name, trigger_id,
    )
    return result != "DELETE 0"


async def list_trigger_prompts(
    conn: asyncpg.Connection, *, trigger_id: str
) -> list[TriggerPromptOut]:
    rows = await conn.fetch(
        """
        SELECT tp.id, tp.template_id, pt.name AS template_name,
               tp.llm_id, lc.provider AS llm_provider, lc.model AS llm_model,
               tp.order_index, tp.enabled
        FROM workspace_extension_trigger_prompts tp
        JOIN prompt_templates pt ON pt.id = tp.template_id
        JOIN workspace_llm_configs lc ON lc.id = tp.llm_id
        WHERE tp.trigger_id = $1::uuid
        ORDER BY tp.order_index
        """,
        trigger_id,
    )
    return [TriggerPromptOut.model_validate(dict(r)) for r in rows]


async def create_trigger_prompt(
    conn: asyncpg.Connection, *, trigger_id: str, req: TriggerPromptCreate
) -> TriggerPromptOut:
    await conn.execute(
        """
        INSERT INTO workspace_extension_trigger_prompts
            (trigger_id, template_id, llm_id, order_index, enabled)
        VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5)
        """,
        trigger_id, str(req.template_id), str(req.llm_id), req.order_index, req.enabled,
    )
    prompts = await list_trigger_prompts(conn, trigger_id=trigger_id)
    result = next(
        (p for p in prompts
         if str(p.template_id) == str(req.template_id) and p.order_index == req.order_index),
        None,
    )
    if result is None:
        raise RuntimeError("trigger prompt not found after insert")
    return result


async def patch_trigger_prompt(
    conn: asyncpg.Connection, *, prompt_id: str, req: TriggerPromptPatch
) -> TriggerPromptOut | None:
    if req.enabled is not None:
        await conn.execute(
            "UPDATE workspace_extension_trigger_prompts SET enabled = $2 "
            "WHERE id = $1::uuid",
            prompt_id, req.enabled,
        )
    if req.order_index is not None:
        await conn.execute(
            "UPDATE workspace_extension_trigger_prompts SET order_index = $2 "
            "WHERE id = $1::uuid",
            prompt_id, req.order_index,
        )
    row = await conn.fetchrow(
        "SELECT trigger_id FROM workspace_extension_trigger_prompts WHERE id=$1::uuid",
        prompt_id,
    )
    if row is None:
        return None
    prompts = await list_trigger_prompts(conn, trigger_id=str(row["trigger_id"]))
    return next((p for p in prompts if str(p.id) == prompt_id), None)


async def delete_trigger_prompt(
    conn: asyncpg.Connection, *, prompt_id: str
) -> bool:
    result = await conn.execute(
        "DELETE FROM workspace_extension_trigger_prompts WHERE id=$1::uuid", prompt_id
    )
    return result != "DELETE 0"
