"""Bascule de fallback par service d'endpoint — lot 2b de l'enabler f94bfd84.

À l'appel d'un service IA (vectorisation, rerank, LLM), le circuit breaker
in-process (`endpoint_breaker`) décide de la cible : primaire tant qu'il
répond, fallback (le service HOMOLOGUE de l'endpoint de fallback déclaré,
migration 090) après `failure_threshold` indisponibilités consécutives,
re-test du primaire après `cooldown_seconds`.

Seule l'INDISPONIBILITÉ compte (connexion refusée, timeout, 5xx —
`is_outage`) : les 429 relèvent du throttling rpm/tpm, les 4xx de
configuration remontent en erreur explicite, jamais de bascule silencieuse.
Sous le seuil, l'erreur remonte telle quelle : la machinerie retry/backoff
existante reste maîtresse. Résolution best-effort : un échec de lecture de la
config de fallback ne casse jamais l'appel primaire.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, TypeVar

import httpx
import structlog

from rag.indexer.providers.protocol import EmbeddingProviderUnreachable
from rag.rerank.protocol import RerankProviderUnreachable
from rag.services.endpoint_breaker import EndpointBreakerRegistry, get_breaker_registry

log = structlog.get_logger(__name__)

T = TypeVar("T")

_SERVICE_COLUMNS = {"vectorization": "indexer", "rerank": "rerank", "llm": "llm"}


@dataclass(frozen=True)
class ServiceSpec:
    """Spec du service homologue de l'endpoint de fallback."""

    provider: str
    model: str
    api_key_ref: str | None
    base_url: str | None
    # Famille d'API du provider (model_dimensions.service) — requis par la
    # factory d'embedding, absent pour rerank/llm.
    provider_service: str | None = None


@dataclass(frozen=True)
class FailoverSpec:
    endpoint_id: str
    failure_threshold: int
    cooldown_seconds: int
    fallback: ServiceSpec | None


def is_outage(exc: BaseException) -> bool:
    """Échec comptabilisé par le breaker : indisponibilité uniquement."""
    if isinstance(exc, EmbeddingProviderUnreachable | RerankProviderUnreachable):
        return True
    if isinstance(exc, httpx.ConnectError | httpx.TimeoutException):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code >= 500
    return False


async def load_failover(
    config_pool: Any, *, workspace_id: Any, service: str
) -> FailoverSpec | None:
    """Spec de bascule du workspace pour un service — via l'endpoint LIÉ
    (`workspaces.endpoint_id`, le snapshot ne porte pas le fallback).
    Best-effort : erreur ou workspace sans endpoint ⇒ None (pas de bascule)."""
    prefix = _SERVICE_COLUMNS[service]
    service_join = (
        "LEFT JOIN model_dimensions fbmd "
        "ON fbmd.provider = fb.indexer_provider AND fbmd.model = fb.indexer_model"
        if service == "vectorization"
        else ""
    )
    fb_service_col = (
        "fbmd.service AS fb_service," if service == "vectorization" else "NULL AS fb_service,"
    )
    try:
        row = await config_pool.fetchrow(
            f"""
            SELECT ve.id AS endpoint_id, ve.failure_threshold, ve.cooldown_seconds,
                   fb.{prefix}_provider AS fb_provider, fb.{prefix}_model AS fb_model,
                   fb.{prefix}_api_key_ref AS fb_api_key_ref,
                   fb.{prefix}_base_url AS fb_base_url,
                   {fb_service_col}
                   ve.fallback_endpoint_id
            FROM workspaces w
            JOIN vault_endpoints ve ON ve.id = w.endpoint_id
            LEFT JOIN vault_endpoints fb ON fb.id = ve.fallback_endpoint_id
            {service_join}
            WHERE w.id = $1
            """,
            workspace_id,
        )
        if row is None:
            return None
        fallback: ServiceSpec | None = None
        if row["fb_provider"] is not None:
            fallback = ServiceSpec(
                provider=row["fb_provider"],
                model=row["fb_model"],
                api_key_ref=row["fb_api_key_ref"],
                base_url=row["fb_base_url"],
                provider_service=row["fb_service"],
            )
        return FailoverSpec(
            endpoint_id=str(row["endpoint_id"]),
            failure_threshold=row["failure_threshold"],
            cooldown_seconds=row["cooldown_seconds"],
            fallback=fallback,
        )
    except Exception as exc:
        # Best-effort : la bascule est une protection, une config illisible ne
        # doit jamais casser l'appel primaire.
        log.warning("endpoint_failover.load_failed", error=type(exc).__name__)
        return None


async def call_with_failover(
    *,
    registry: EndpointBreakerRegistry | None = None,
    spec: FailoverSpec | None,
    service: str,
    primary: Callable[[], Awaitable[T]],
    fallback_call: Callable[[ServiceSpec], Awaitable[T]],
) -> T:
    """Exécute l'appel avec la machine à états du breaker.

    - pas de spec ou pas de fallback déclaré : passthrough (comportement
      actuel inchangé) ;
    - circuit ouvert : fallback direct (le primaire n'est pas appelé) ;
    - échec d'indisponibilité : comptabilisé ; si le seuil ouvre le circuit,
      CET appel est servi par le fallback, sinon l'erreur remonte (retry
      existant) ; un échec du fallback remonte tel quel (pas de cascade).
    """
    if spec is None or spec.fallback is None:
        return await primary()
    reg = registry if registry is not None else get_breaker_registry()
    ep = spec.endpoint_id
    if reg.target(ep, service) == "fallback":
        return await fallback_call(spec.fallback)
    try:
        result = await primary()
    except Exception as exc:
        if not is_outage(exc):
            raise
        reg.record_failure(
            ep,
            service,
            failure_threshold=spec.failure_threshold,
            cooldown_seconds=spec.cooldown_seconds,
        )
        if reg.target(ep, service) == "fallback":
            log.warning(
                "endpoint_failover.switched",
                endpoint_id=ep,
                service=service,
                fallback_provider=spec.fallback.provider,
                error=type(exc).__name__,
            )
            return await fallback_call(spec.fallback)
        raise
    reg.record_success(ep, service)
    return result
