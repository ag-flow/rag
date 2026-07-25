from __future__ import annotations

from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status

from rag.api.workspace_access import require_owned_workspace_id
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import get_current_owner_id
from rag.schemas.enrichments import (
    PromptTemplateCreate,
    PromptTemplateOut,
    PromptTemplatePatch,
    TriggerCreate,
    TriggerOut,
    TriggerPatch,
    TriggerPromptCreate,
    TriggerPromptOut,
    TriggerPromptPatch,
)

log = structlog.get_logger(__name__)

_auth = [Depends(require_master_key_or_authenticated_admin)]

# ─── Référentiel des langues ──────────────────────────────────────────────────

router_languages = APIRouter(
    prefix="/api/admin/config/languages",
    tags=["config-languages"],
    dependencies=_auth,
)


@router_languages.get("", response_model=list[dict])
async def list_languages(request: Request) -> list[dict]:
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT code, label, built_in FROM languages ORDER BY code"
        )
    return [dict(r) for r in rows]


def _pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


# ─── Bibliothèque de prompts (système + utilisateur, spec chunking §4) ────────

router_prompts = APIRouter(
    prefix="/api/admin/prompts",
    tags=["enrichment-prompts"],
    dependencies=_auth,
)


@router_prompts.get("", response_model=list[PromptTemplateOut])
async def list_prompts(request: Request) -> list[PromptTemplateOut]:
    from rag.services.prompt_templates import list_prompt_templates
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        return await list_prompt_templates(conn, owner_id=owner_id)


@router_prompts.post("", response_model=PromptTemplateOut, status_code=201)
async def create_prompt(body: PromptTemplateCreate, request: Request) -> PromptTemplateOut:
    from rag.services.prompt_templates import InvalidLanguageError, create_prompt_template
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        try:
            return await create_prompt_template(conn, owner_id=owner_id, req=body)
        except InvalidLanguageError as exc:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "error": "invalid_language",
                    "language": exc.language,
                    "valid_codes": exc.valid_codes,
                },
            ) from exc
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "name already exists") from exc
            raise


@router_prompts.get("/{template_id}", response_model=PromptTemplateOut)
async def get_prompt(template_id: UUID, request: Request) -> PromptTemplateOut:
    from rag.services.prompt_templates import get_prompt_template
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        result = await get_prompt_template(conn, owner_id=owner_id, template_id=str(template_id))
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found")
    return result


@router_prompts.patch("/{template_id}", response_model=PromptTemplateOut)
async def patch_prompt(
    template_id: UUID, body: PromptTemplatePatch, request: Request
) -> PromptTemplateOut:
    from rag.services.prompt_templates import (
        TemplateImmutableError,
        TemplateNotFoundError,
        patch_prompt_template,
    )
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        try:
            return await patch_prompt_template(
                conn, owner_id=owner_id, template_id=str(template_id), req=body
            )
        except TemplateNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found") from exc
        except TemplateImmutableError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "template système non modifiable"
            ) from exc


@router_prompts.delete("/{template_id}", status_code=204)
async def delete_prompt(template_id: UUID, request: Request) -> Response:
    from rag.services.prompt_templates import (
        TemplateImmutableError,
        TemplateInUseError,
        TemplateNotFoundError,
        delete_prompt_template,
    )
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        try:
            await delete_prompt_template(
                conn, owner_id=owner_id, template_id=str(template_id)
            )
        except TemplateNotFoundError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "template not found") from exc
        except TemplateImmutableError as exc:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, "template système non supprimable"
            ) from exc
        except TemplateInUseError as exc:
            raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ─── Triggers par workspace ────────────────────────────────────────────────────

router_triggers = APIRouter(
    prefix="/api/admin/workspaces/{workspace_name}/triggers",
    tags=["enrichment-triggers"],
    dependencies=_auth,
)


@router_triggers.get("", response_model=list[TriggerOut])
async def list_triggers(workspace_name: str, request: Request) -> list[TriggerOut]:
    from rag.services.triggers import list_triggers as _list
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        return await _list(conn, workspace_name=workspace_name)


@router_triggers.post("", response_model=TriggerOut, status_code=201)
async def create_trigger(
    workspace_name: str, body: TriggerCreate, request: Request
) -> TriggerOut:
    from rag.services.triggers import UnknownTriggerStrategyError
    from rag.services.triggers import create_trigger as _create
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        try:
            return await _create(
                conn, workspace_name=workspace_name, req=body, owner_id=owner_id
            )
        except UnknownTriggerStrategyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
        except Exception as exc:
            if "unique" in str(exc).lower():
                msg = "extension already has trigger"
                raise HTTPException(status.HTTP_409_CONFLICT, msg) from exc
            raise


@router_triggers.patch("/{trigger_id}", response_model=TriggerOut)
async def patch_trigger(
    workspace_name: str, trigger_id: UUID, body: TriggerPatch, request: Request
) -> TriggerOut:
    from rag.services.triggers import UnknownTriggerStrategyError
    from rag.services.triggers import patch_trigger as _patch
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    owner_id = get_current_owner_id(request)
    async with _pool(request).acquire() as conn:
        try:
            result = await _patch(
                conn,
                workspace_name=workspace_name,
                trigger_id=str(trigger_id),
                req=body,
                owner_id=owner_id,
            )
        except UnknownTriggerStrategyError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger not found")
    return result


@router_triggers.delete("/{trigger_id}", status_code=204)
async def delete_trigger(
    workspace_name: str, trigger_id: UUID, request: Request
) -> Response:
    from rag.services.triggers import delete_trigger as _delete
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        deleted = await _delete(conn, workspace_name=workspace_name, trigger_id=str(trigger_id))
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router_triggers.get("/{trigger_id}/prompts", response_model=list[TriggerPromptOut])
async def list_trigger_prompts(
    workspace_name: str, trigger_id: UUID, request: Request
) -> list[TriggerPromptOut]:
    from rag.services.triggers import list_trigger_prompts as _list
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        return await _list(conn, trigger_id=str(trigger_id))


@router_triggers.post("/{trigger_id}/prompts", response_model=TriggerPromptOut, status_code=201)
async def create_trigger_prompt(
    workspace_name: str, trigger_id: UUID, body: TriggerPromptCreate, request: Request
) -> TriggerPromptOut:
    from rag.services.triggers import create_trigger_prompt as _create
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        try:
            return await _create(conn, trigger_id=str(trigger_id), req=body)
        except Exception as exc:
            if "unique" in str(exc).lower():
                raise HTTPException(status.HTTP_409_CONFLICT, "order_index already used") from exc
            raise


@router_triggers.patch("/{trigger_id}/prompts/{prompt_id}", response_model=TriggerPromptOut)
async def patch_trigger_prompt(
    workspace_name: str,
    trigger_id: UUID,
    prompt_id: UUID,
    body: TriggerPromptPatch,
    request: Request,
) -> TriggerPromptOut:
    from rag.services.triggers import patch_trigger_prompt as _patch
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        result = await _patch(conn, prompt_id=str(prompt_id), req=body)
    if result is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger prompt not found")
    return result


@router_triggers.delete("/{trigger_id}/prompts/{prompt_id}", status_code=204)
async def delete_trigger_prompt(
    workspace_name: str, trigger_id: UUID, prompt_id: UUID, request: Request
) -> Response:
    from rag.services.triggers import delete_trigger_prompt as _delete
    await require_owned_workspace_id(request, workspace_name, _pool(request))
    async with _pool(request).acquire() as conn:
        deleted = await _delete(conn, prompt_id=str(prompt_id))
    if not deleted:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "trigger prompt not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)
