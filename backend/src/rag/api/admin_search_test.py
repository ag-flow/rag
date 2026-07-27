from __future__ import annotations

from typing import Any
from uuid import UUID

import asyncpg
import structlog
from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field

from rag.api.playground_search import perform_workspace_search
from rag.api.workspace_access import require_owned_workspace_id
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.services import search_test as svc

log = structlog.get_logger(__name__)

router = APIRouter(
    prefix="/api/workspaces/{workspace_name}/search-test",
    tags=["search-test"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


class QuestionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=3, max_length=2000)
    expected_path_contains: str = Field(min_length=3, max_length=500)
    family: str = "libre"


class QuestionPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


async def _ws_id(request: Request, workspace_name: str) -> UUID:
    pool: asyncpg.Pool = request.app.state.pools.config_pool
    return await require_owned_workspace_id(request, workspace_name, pool)


@router.get("/questions")
async def list_questions(workspace_name: str, request: Request) -> list[dict[str, Any]]:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    return await svc.list_questions(pool, workspace_id=ws_id)


@router.post("/questions", status_code=201)
async def create_question(
    workspace_name: str, body: QuestionCreate, request: Request
) -> dict[str, Any]:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    try:
        return await svc.upsert_question(
            pool,
            workspace_id=ws_id,
            question=body.question,
            expected_path_contains=body.expected_path_contains,
            family=body.family,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc


@router.patch("/questions/{question_id}")
async def patch_question(
    workspace_name: str, question_id: UUID, body: QuestionPatch, request: Request
) -> Response:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    ok = await svc.set_question_enabled(
        pool, workspace_id=ws_id, question_id=question_id, enabled=body.enabled
    )
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/questions/{question_id}", status_code=204)
async def delete_question(workspace_name: str, question_id: UUID, request: Request) -> Response:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    ok = await svc.delete_question(pool, workspace_id=ws_id, question_id=question_id)
    if not ok:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "question not found")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/runs", status_code=201)
async def run_campaign(workspace_name: str, request: Request) -> dict[str, Any]:
    """Lance la campagne (déclenchement IHM — spec architecte) : chaque
    question activée passe par la recherche du produit, le run est persisté."""
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool

    from rag.services.mcp import _load_hybrid_config

    hybrid = await _load_hybrid_config(pool, ws_id)
    config: dict[str, Any] = (
        {
            "hybrid": bool(hybrid["enabled"]),
            "lexical_engine": hybrid["lexical_engine"],
            "weight_vector": float(hybrid["weight_vector"]),
            "weight_lexical": float(hybrid["weight_lexical"]),
            "rrf_k": int(hybrid["rrf_k"]),
        }
        if hybrid is not None
        else {"hybrid": False}
    )

    async def search_fn(question: str) -> list[str]:
        resp = await perform_workspace_search(
            request, workspace_name, query=question, top_k=10, min_score=0.0
        )
        return [h.path for h in resp.hits]

    try:
        run = await svc.run_campaign(pool, workspace_id=ws_id, search_fn=search_fn, config=config)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return run


@router.get("/runs")
async def list_runs(workspace_name: str, request: Request) -> list[dict[str, Any]]:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    return await svc.list_runs(pool, workspace_id=ws_id)


@router.get("/runs/{run_id}")
async def get_run(workspace_name: str, run_id: UUID, request: Request) -> dict[str, Any]:
    ws_id = await _ws_id(request, workspace_name)
    pool = request.app.state.pools.config_pool
    run = await svc.get_run(pool, workspace_id=ws_id, run_id=run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run
