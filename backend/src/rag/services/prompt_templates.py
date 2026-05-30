from __future__ import annotations

import asyncpg
import structlog

from rag.schemas.enrichments import PromptTemplateCreate, PromptTemplateOut, PromptTemplatePatch

log = structlog.get_logger(__name__)


async def list_prompt_templates(conn: asyncpg.Connection) -> list[PromptTemplateOut]:
    rows = await conn.fetch(
        "SELECT id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at "
        "FROM prompt_templates ORDER BY language, name"
    )
    return [PromptTemplateOut.model_validate(dict(r)) for r in rows]


async def get_prompt_template(
    conn: asyncpg.Connection, template_id: str
) -> PromptTemplateOut | None:
    row = await conn.fetchrow(
        "SELECT id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at "
        "FROM prompt_templates WHERE id = $1::uuid",
        template_id,
    )
    return PromptTemplateOut.model_validate(dict(row)) if row else None


async def create_prompt_template(
    conn: asyncpg.Connection, req: PromptTemplateCreate
) -> PromptTemplateOut:
    import json
    row = await conn.fetchrow(
        "INSERT INTO prompt_templates "
        "(name, language, description, metadata_key, result_type, result_schema, prompt) "
        "VALUES ($1, $2, $3, $4, $5, $6::jsonb, $7) "
        "RETURNING id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at",
        req.name, req.language, req.description, req.metadata_key,
        req.result_type,
        json.dumps(req.result_schema) if req.result_schema else None,
        req.prompt,
    )
    log.info("prompt_template.created", name=req.name)
    return PromptTemplateOut.model_validate(dict(row))


async def patch_prompt_template(
    conn: asyncpg.Connection, template_id: str, req: PromptTemplatePatch
) -> PromptTemplateOut | None:
    import json
    row = await conn.fetchrow(
        "UPDATE prompt_templates SET "
        "description = COALESCE($2, description), "
        "prompt = COALESCE($3, prompt), "
        "result_schema = COALESCE($4::jsonb, result_schema), "
        "updated_at = now() "
        "WHERE id = $1::uuid "
        "RETURNING id, name, language, description, metadata_key, result_type, "
        "result_schema, prompt, created_at, updated_at",
        template_id,
        req.description,
        req.prompt,
        json.dumps(req.result_schema) if req.result_schema else None,
    )
    return PromptTemplateOut.model_validate(dict(row)) if row else None


async def delete_prompt_template(
    conn: asyncpg.Connection, template_id: str
) -> bool:
    """Supprime si non référencé par un trigger. Retourne False si référencé."""
    ref_count = await conn.fetchval(
        "SELECT count(*) FROM workspace_extension_trigger_prompts WHERE template_id = $1::uuid",
        template_id,
    )
    if int(ref_count or 0) > 0:
        return False
    result = await conn.execute(
        "DELETE FROM prompt_templates WHERE id = $1::uuid", template_id
    )
    return result != "DELETE 0"
