from __future__ import annotations

import asyncpg
from fastapi import APIRouter, Depends, Query, Request, Response, status

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.schemas.webhooks import (
    WebhookCallOut,
    WebhookCreateRequest,
    WebhookHeaderPatchRequest,
    WebhookOut,
    WebhookPatchRequest,
)
from rag.services.webhooks import (
    create_webhook,
    delete_webhook,
    list_webhook_calls,
    list_webhooks,
    patch_webhook,
    patch_webhook_header,
    purge_old_webhook_calls,
)


def _config_pool(request: Request) -> asyncpg.Pool:
    return request.app.state.pools.config_pool  # type: ignore[no-any-return]


def _resolver(request: Request) -> object:
    return getattr(request.app.state, "resolver", None)


def build_webhooks_router() -> APIRouter:
    router = APIRouter(
        tags=["webhooks"],
        dependencies=[Depends(require_master_key_or_authenticated_admin)],
    )

    @router.get("/workspaces/{name}/webhooks/calls", response_model=list[WebhookCallOut])
    async def get_calls(
        name: str,
        webhook_id: str | None = Query(default=None),
        correlation_id: str | None = Query(default=None),
        status_filter: str | None = Query(default=None, alias="status"),
        limit: int = Query(default=50, ge=1, le=500),
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> list[dict]:
        return await list_webhook_calls(
            pool,
            workspace_name=name,
            webhook_id=webhook_id,
            correlation_id=correlation_id,
            status_filter=status_filter,
            limit=limit,
        )

    @router.delete("/workspaces/{name}/webhooks/calls", status_code=204)
    async def purge_calls(
        name: str,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> Response:
        await purge_old_webhook_calls(pool)
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.get("/workspaces/{name}/webhooks", response_model=list[WebhookOut])
    async def get_webhooks(
        name: str,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> list[dict]:
        return await list_webhooks(pool, workspace_name=name)

    @router.post("/workspaces/{name}/webhooks", response_model=WebhookOut, status_code=201)
    async def post_webhook(
        name: str,
        body: WebhookCreateRequest,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await create_webhook(
            pool,
            workspace_name=name,
            name=body.name,
            url=body.url,
            enabled=body.enabled,
            headers=[h.model_dump() for h in body.headers],
            resolver=_resolver(request),
        )

    @router.patch("/workspaces/{name}/webhooks/{webhook_id}", response_model=WebhookOut)
    async def update_webhook(
        name: str,
        webhook_id: str,
        body: WebhookPatchRequest,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await patch_webhook(
            pool,
            webhook_id=webhook_id,
            name=body.name,
            url=body.url,
            enabled=body.enabled,
        )

    @router.delete("/workspaces/{name}/webhooks/{webhook_id}", status_code=204)
    async def remove_webhook(
        name: str,
        webhook_id: str,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> Response:
        await delete_webhook(pool, webhook_id=webhook_id, resolver=_resolver(request))
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    @router.patch(
        "/workspaces/{name}/webhooks/{webhook_id}/headers/{header_id}",
        response_model=dict,
    )
    async def update_header(
        name: str,
        webhook_id: str,
        header_id: str,
        body: WebhookHeaderPatchRequest,
        request: Request,
        pool: asyncpg.Pool = Depends(_config_pool),  # noqa: B008
    ) -> dict:
        return await patch_webhook_header(
            pool,
            webhook_id=webhook_id,
            header_id=header_id,
            value=body.value,
            vault=body.vault,
            enabled=body.enabled,
            workspace_name=name,
            resolver=_resolver(request),
        )

    return router
