from __future__ import annotations

from contextvars import ContextVar
from typing import Any

import asyncpg
import structlog
from pydantic import ValidationError

from rag.api.mcp_endpoint_support import (
    SERVICES,
    build_service_update,
    service_summary,
)
from rag.api.mcp_library_support import dump
from rag.schemas.vault_endpoints import EndpointOut
from rag.services import vault_endpoints as endpoints_svc

log = structlog.get_logger(__name__)

ENDPOINT_ADMIN_REFUSAL = (
    "Accès refusé : l'administration des endpoints (ressource hors workspace) "
    "exige une clé de niveau 'admin'."
)
_NOT_VAULT_OWNER = (
    "Coffre '{vault}' en lecture seule pour cette clé : seuls les endpoints "
    "des coffres dont tu es propriétaire sont modifiables."
)
_UNKNOWN_VAULT = (
    "Coffre '{vault}' introuvable ou invisible. Appelle list_endpoints() pour "
    "les coffres accessibles (les tiens + le coffre par défaut)."
)
_UNKNOWN_ENDPOINT = (
    "Endpoint '{endpoint}' introuvable dans le coffre '{vault}'. "
    "Appelle list_endpoints() pour les slugs disponibles."
)

_VISIBLE_VAULTS = (
    "SELECT id, name, label, is_default, owner_id FROM harpocrate_vaults "
    "WHERE is_default = true OR owner_id = $1 ORDER BY created_at"
)
_VAULT_BY_NAME = (
    "SELECT id, name, label, is_default, owner_id FROM harpocrate_vaults "
    "WHERE (is_default = true OR owner_id = $1) AND name = $2"
)


def register_endpoint_tools(mcp: Any, ws_ctx: ContextVar[Any]) -> None:
    """Outils MCP d'administration des endpoints IA (coffres Harpocrate).

    Un endpoint = préréglage nommé des 3 services IA (vectorisation, rerank,
    LLM) porté par un coffre. Visibilité : coffres du caller + coffre par
    défaut. Écriture : coffres du caller uniquement. Tout exige scope admin
    (ressource hors workspace, décision 2026-07-26). Les valeurs de secrets ne
    transitent jamais — uniquement des noms de refs (api_key_ref).
    """

    def _refusal(ctx: Any) -> str | None:
        return None if ctx.scope == "admin" else ENDPOINT_ADMIN_REFUSAL

    async def _vault(conn: asyncpg.Connection, ctx: Any, vault: str) -> asyncpg.Record | None:
        return await conn.fetchrow(_VAULT_BY_NAME, ctx.owner_id, vault)

    async def _endpoint(
        conn: asyncpg.Connection, vault_id: Any, endpoint: str
    ) -> EndpointOut | None:
        eps = await endpoints_svc.list_endpoints(conn, vault_id=vault_id)
        return next((e for e in eps if e.slug == endpoint), None)

    @mcp.tool()
    async def list_endpoints() -> str:
        """Liste les endpoints IA accessibles, groupés par coffre Harpocrate.

        Un endpoint est un préréglage nommé des services IA (vectorisation,
        rerank, LLM) servant de source à la création de workspaces. Visibilité :
        tes coffres + le coffre par défaut de l'instance ; `writable` indique si
        cette clé peut modifier l'endpoint (coffre possédé). Requiert une clé
        de niveau 'admin'.

        Sortie : JSON [{vault, vault_label, writable, endpoints: [{slug, label,
        services: {vectorization|rerank|llm: {provider, model} | null}}]}].
        Lecture seule. Détail complet via get_endpoint_configuration(vault, slug).
        """
        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        async with ctx.config_pool.acquire() as conn:
            vaults = await conn.fetch(_VISIBLE_VAULTS, ctx.owner_id)
            result = []
            for v in vaults:
                eps = await endpoints_svc.list_endpoints(conn, vault_id=v["id"])
                result.append(
                    {
                        "vault": v["name"],
                        "vault_label": v["label"],
                        "writable": v["owner_id"] == ctx.owner_id,
                        "endpoints": [
                            {"slug": e.slug, "label": e.label, "services": service_summary(e)}
                            for e in eps
                        ],
                    }
                )
        return dump(result)

    @mcp.tool()
    async def get_endpoint_configuration(vault: str, endpoint: str) -> str:
        """Configuration complète d'un endpoint : services, paramètres, quotas.

        - vault    : nom du coffre Harpocrate (voir list_endpoints)
        - endpoint : slug de l'endpoint dans ce coffre

        Sortie : JSON {slug, label, indexer, rerank, llm} — chaque service
        expose provider, model, api_key_ref (nom de la ref, jamais le secret),
        base_url et les quotas rpm_limit/tpm_limit (null = pas de limite) ;
        le rerank porte aussi top_k_pre_rerank. Requiert une clé 'admin'.
        Lecture seule.
        """
        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        async with ctx.config_pool.acquire() as conn:
            v = await _vault(conn, ctx, vault)
            if v is None:
                return _UNKNOWN_VAULT.format(vault=vault)
            ep = await _endpoint(conn, v["id"], endpoint)
        if ep is None:
            return _UNKNOWN_ENDPOINT.format(endpoint=endpoint, vault=vault)
        payload = ep.model_dump(mode="json")
        payload.pop("id", None)
        payload.pop("vault_id", None)
        return dump({"vault": vault, "writable": v["owner_id"] == ctx.owner_id, **payload})

    @mcp.tool()
    async def configure_endpoint_service(
        vault: str,
        endpoint: str,
        service: str,
        provider: str | None = None,
        model: str | None = None,
        api_key_ref: str | None = None,
        base_url: str | None = None,
        rpm_limit: int | None = None,
        tpm_limit: int | None = None,
        top_k_pre_rerank: int | None = None,
        clear: bool = False,
    ) -> str:
        """Configure un service (vectorization | rerank | llm) d'un endpoint.

        Mise à jour PARTIELLE : un paramètre omis conserve sa valeur. Pour
        créer une section absente (ex. premier rerank), `provider` et `model`
        sont requis. Effacement explicite : api_key_ref="" ou base_url=""
        retire la valeur ; rpm_limit=0 ou tpm_limit=0 désactive la limite ;
        clear=true supprime toute la section (rerank et llm uniquement — la
        vectorisation est obligatoire). `api_key_ref` est un NOM de secret du
        coffre, jamais une valeur.

        Effet différé (snapshot) : les workspaces existants gardent leur
        configuration copiée — la modification ne s'applique qu'aux workspaces
        créés ensuite, ou après reset_workspace_from_endpoint. Requiert une
        clé 'admin' ET la propriété du coffre.

        Sortie : configuration mise à jour (même format que
        get_endpoint_configuration) ou message d'erreur explicite.
        """
        ctx = ws_ctx.get()
        refusal = _refusal(ctx)
        if refusal:
            return refusal
        if service not in SERVICES:
            return f"Service inconnu : '{service}'. Valeurs possibles : {', '.join(SERVICES)}."
        async with ctx.config_pool.acquire() as conn:
            v = await _vault(conn, ctx, vault)
            if v is None:
                return _UNKNOWN_VAULT.format(vault=vault)
            if v["owner_id"] != ctx.owner_id:
                return _NOT_VAULT_OWNER.format(vault=vault)
            ep = await _endpoint(conn, v["id"], endpoint)
            if ep is None:
                return _UNKNOWN_ENDPOINT.format(endpoint=endpoint, vault=vault)

            try:
                update = build_service_update(
                    ep,
                    service=service,
                    clear=clear,
                    provider=provider,
                    model=model,
                    api_key_ref=api_key_ref,
                    base_url=base_url,
                    rpm_limit=rpm_limit,
                    tpm_limit=tpm_limit,
                    top_k_pre_rerank=top_k_pre_rerank,
                )
            except (ValidationError, ValueError) as exc:
                return f"Paramètres invalides : {exc}"

            updated = await endpoints_svc.update_endpoint(conn, endpoint_id=ep.id, req=update)
        if updated is None:  # pragma: no cover — l'endpoint vient d'être résolu
            return _UNKNOWN_ENDPOINT.format(endpoint=endpoint, vault=vault)
        log.info(
            "mcp.endpoint_service_configured",
            vault=vault,
            endpoint=endpoint,
            service=service,
            owner=ctx.owner_id[:8],
        )
        payload = updated.model_dump(mode="json")
        payload.pop("id", None)
        payload.pop("vault_id", None)
        return dump(
            {
                "vault": vault,
                **payload,
                "note": (
                    "Snapshot : les workspaces existants ne sont pas modifiés. "
                    "Utilise reset_workspace_from_endpoint(workspace) pour propager."
                ),
            }
        )
