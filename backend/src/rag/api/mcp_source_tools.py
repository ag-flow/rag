from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import structlog
from fastapi import HTTPException
from pydantic import ValidationError

from rag.api.mcp_library_support import dump
from rag.schemas.admin import SourceCreateRequest
from rag.services import sources as sources_svc
from rag.services import workspaces as workspaces_svc

log = structlog.get_logger(__name__)

SOURCE_ADMIN_REFUSAL = (
    "Accès refusé : la gestion des sources git d'un workspace exige une clé "
    "de niveau 'admin'."
)
_UNKNOWN_WS = (
    "Workspace '{ws}' introuvable. Appelle list_workspaces() pour les slugs accessibles."
)


def register_source_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP de gestion des sources git d'un workspace.

    Mêmes services que l'API REST (services/sources.py). Les credentials sont
    des REFS Harpocrate déjà existantes (jamais de valeur de secret) ; une ref
    inaccessible au caller est refusée.
    """

    async def _owned(ctx: Any, workspace: str) -> bool:
        async with ctx.config_pool.acquire() as conn:
            ws_id = await workspaces_svc.resolve_owned_workspace_id(
                conn, name=workspace, owner_id=ctx.owner_id
            )
        return ws_id is not None

    @mcp.tool()
    async def list_git_sources(workspace: str) -> str:
        """Sources git d'un workspace (URL, branche, filtres, sync, webhook).

        - workspace : slug du workspace (voir list_workspaces)

        Sortie : JSON [{id, name, type, config, last_indexed_at, created_at,
        webhook_enabled}] — config contient url, branch, include/exclude
        (globs), sync_interval_seconds et les refs d'auth (noms, pas de
        secrets). Lecture seule, toute clé valide.
        """
        ctx = ws_ctx.get()
        if not await _owned(ctx, workspace):
            return _UNKNOWN_WS.format(ws=workspace)
        rows = await sources_svc.list_sources(ctx.config_pool, workspace_name=workspace)
        return dump(rows)

    @mcp.tool()
    async def add_git_source(
        workspace: str,
        name: str,
        url: str,
        branch: str | None = None,
        include: list[str] | None = None,
        exclude: list[str] | None = None,
        sync_interval_seconds: int | None = None,
        git_provider: str | None = None,
        auth_type: str | None = None,
        auth_ref: str | None = None,
        ssh_key_ref: str | None = None,
        ssh_username: str | None = None,
    ) -> str:
        """Ajoute une source git à un workspace (synchronisée par le worker).

        - workspace : slug du workspace (voir list_workspaces)
        - name      : nom de la source (minuscules, chiffres, `_`, `-`)
        - url       : URL du dépôt (https://... ou git@...)
        - branch    : branche à suivre (défaut : branche par défaut du dépôt,
          détectée automatiquement)
        - include / exclude : patterns glob sur le chemin complet
          (`**/*.md`, `docs/**`) — défaut : tout inclure
        - sync_interval_seconds : période de synchronisation du worker
        - git_provider : github | azure-devops | autre (informatif)
        - auth_type    : token | ssh — dépôt privé uniquement
        - auth_ref / ssh_key_ref : REF d'un credential Harpocrate existant
          (nom, jamais la valeur) ; la ref doit être accessible au caller
        - ssh_username : utilisateur SSH si auth_type=ssh

        La première synchronisation est planifiée immédiatement. Requiert une
        clé 'admin'. Sortie : JSON de la source créée (+ branch_warning si la
        branche n'a pas pu être détectée).
        """
        ctx = ws_ctx.get()
        if ctx.scope != "admin":
            return SOURCE_ADMIN_REFUSAL
        if ctx.vaults_service is None:
            return "Service indisponible : gestion des sources non initialisée."
        if not await _owned(ctx, workspace):
            return _UNKNOWN_WS.format(ws=workspace)

        config: dict[str, Any] = {"url": url}
        if branch:
            config["branch"] = branch
        if include:
            config["include"] = include
        if exclude:
            config["exclude"] = exclude
        if sync_interval_seconds is not None:
            config["sync_interval_seconds"] = sync_interval_seconds
        try:
            request = SourceCreateRequest(
                name=name,
                type="git",
                git_provider=git_provider,
                auth_type=auth_type,  # type: ignore[arg-type]
                auth_ref=auth_ref,
                ssh_key_ref=ssh_key_ref,
                ssh_username=ssh_username,
                config=config,
            )
        except ValidationError as exc:
            return f"Paramètres invalides : {exc}"
        try:
            result = await sources_svc.add_source(
                workspace_name=workspace,
                request=request,
                config_pool=ctx.config_pool,
                harpocrate_vaults_service=ctx.vaults_service,
                owner_id=ctx.owner_id,
                resolver=ctx.resolver,
            )
        except HTTPException as exc:
            return (
                f"Refusé : {exc.detail}. La ref d'auth doit exister dans un coffre "
                "accessible (le tien ou le coffre par défaut)."
            )
        log.info("mcp.source_added", workspace=workspace, source=name, owner=ctx.owner_id[:8])
        return dump(result)
