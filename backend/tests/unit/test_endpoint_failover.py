"""Bascule de fallback par service (lot 2b de l'enabler f94bfd84) : prédicat
d'indisponibilité, résolution best-effort et wrapper primaire/fallback piloté
par le circuit breaker."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import uuid4

import httpx
import pytest

from rag.indexer.providers.protocol import (
    EmbeddingProviderUnreachable,
    EmbeddingRateLimited,
)
from rag.rerank.protocol import RerankAuthError, RerankProviderUnreachable
from rag.services.endpoint_breaker import EndpointBreakerRegistry
from rag.services.endpoint_failover import (
    FailoverSpec,
    ServiceSpec,
    call_with_failover,
    is_outage,
    load_failover,
)


class TestIsOutage:
    def test_unreachable_and_timeouts_qualify(self) -> None:
        assert is_outage(EmbeddingProviderUnreachable("down"))
        assert is_outage(RerankProviderUnreachable("down"))
        assert is_outage(httpx.ConnectError("refused"))
        assert is_outage(httpx.ReadTimeout("slow"))

    def test_5xx_qualifies_but_4xx_and_429_do_not(self) -> None:
        def _status_error(code: int) -> httpx.HTTPStatusError:
            resp = httpx.Response(code, request=httpx.Request("GET", "http://x"))
            return httpx.HTTPStatusError("boom", request=resp.request, response=resp)

        assert is_outage(_status_error(503))
        assert not is_outage(_status_error(401))
        assert not is_outage(_status_error(429))
        assert not is_outage(EmbeddingRateLimited("429"))
        assert not is_outage(RerankAuthError("bad key"))
        assert not is_outage(ValueError("config"))


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _spec(fallback: bool = True) -> FailoverSpec:
    return FailoverSpec(
        endpoint_id="ep-1",
        failure_threshold=2,
        cooldown_seconds=60,
        fallback=(
            ServiceSpec(
                provider="ollama",
                model="text-embedding-3-large",
                api_key_ref=None,
                base_url="http://mirror:11434",
                provider_service="openai-compatible",
            )
            if fallback
            else None
        ),
    )


class TestCallWithFailover:
    @pytest.mark.asyncio
    async def test_primary_success_passthrough(self) -> None:
        reg = EndpointBreakerRegistry(clock=_Clock())
        out = await call_with_failover(
            registry=reg,
            spec=_spec(),
            service="vectorization",
            primary=AsyncMock(return_value="ok"),
            fallback_call=AsyncMock(side_effect=AssertionError("pas de fallback attendu")),
        )
        assert out == "ok"
        assert reg.state("ep-1", "vectorization") == "closed"

    @pytest.mark.asyncio
    async def test_switches_to_fallback_at_threshold(self) -> None:
        reg = EndpointBreakerRegistry(clock=_Clock())
        primary = AsyncMock(side_effect=EmbeddingProviderUnreachable("down"))
        fallback = AsyncMock(return_value="secours")

        # 1er échec : sous le seuil → l'erreur remonte (machinerie retry).
        with pytest.raises(EmbeddingProviderUnreachable):
            await call_with_failover(
                registry=reg,
                spec=_spec(),
                service="vectorization",
                primary=primary,
                fallback_call=fallback,
            )
        # 2e échec : seuil atteint → bascule immédiate sur le fallback.
        out = await call_with_failover(
            registry=reg,
            spec=_spec(),
            service="vectorization",
            primary=primary,
            fallback_call=fallback,
        )
        assert out == "secours"
        assert reg.state("ep-1", "vectorization") == "open"
        # Appel suivant : circuit ouvert → fallback direct, primaire non appelé.
        primary.reset_mock()
        out = await call_with_failover(
            registry=reg,
            spec=_spec(),
            service="vectorization",
            primary=primary,
            fallback_call=fallback,
        )
        assert out == "secours"
        primary.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_half_open_success_returns_to_primary(self) -> None:
        clock = _Clock()
        reg = EndpointBreakerRegistry(clock=clock)
        failing = AsyncMock(side_effect=EmbeddingProviderUnreachable("down"))
        fallback = AsyncMock(return_value="secours")
        for _ in range(2):
            try:
                await call_with_failover(
                    registry=reg,
                    spec=_spec(),
                    service="vectorization",
                    primary=failing,
                    fallback_call=fallback,
                )
            except EmbeddingProviderUnreachable:
                pass
        clock.now += 61  # cooldown écoulé → half-open, l'appel teste le primaire
        healthy = AsyncMock(return_value="reprise")
        out = await call_with_failover(
            registry=reg,
            spec=_spec(),
            service="vectorization",
            primary=healthy,
            fallback_call=fallback,
        )
        assert out == "reprise"
        assert reg.state("ep-1", "vectorization") == "closed"

    @pytest.mark.asyncio
    async def test_non_outage_error_never_switches(self) -> None:
        reg = EndpointBreakerRegistry(clock=_Clock())
        with pytest.raises(EmbeddingRateLimited):
            await call_with_failover(
                registry=reg,
                spec=_spec(),
                service="vectorization",
                primary=AsyncMock(side_effect=EmbeddingRateLimited("429")),
                fallback_call=AsyncMock(),
            )
        assert reg.state("ep-1", "vectorization") == "closed"

    @pytest.mark.asyncio
    async def test_no_spec_or_no_fallback_is_passthrough(self) -> None:
        reg = EndpointBreakerRegistry(clock=_Clock())
        primary = AsyncMock(side_effect=EmbeddingProviderUnreachable("down"))
        with pytest.raises(EmbeddingProviderUnreachable):
            await call_with_failover(
                registry=reg,
                spec=None,
                service="vectorization",
                primary=primary,
                fallback_call=AsyncMock(),
            )
        with pytest.raises(EmbeddingProviderUnreachable):
            await call_with_failover(
                registry=reg,
                spec=_spec(fallback=False),
                service="vectorization",
                primary=primary,
                fallback_call=AsyncMock(),
            )


class TestLoadFailover:
    @pytest.mark.asyncio
    async def test_loads_homologous_service_spec(self) -> None:
        ep = uuid4()
        pool = SimpleNamespace(
            fetchrow=AsyncMock(
                return_value={
                    "endpoint_id": ep,
                    "failure_threshold": 3,
                    "cooldown_seconds": 60,
                    "fb_provider": "ollama",
                    "fb_model": "m",
                    "fb_api_key_ref": None,
                    "fb_base_url": "http://mirror",
                    "fb_service": "openai-compatible",
                    "fb_endpoint_id": uuid4(),
                    "fb_rpm_limit": 100,
                    "fb_tpm_limit": None,
                    "fb_max_concurrency": 2,
                }
            )
        )
        spec = await load_failover(pool, workspace_id=uuid4(), service="rerank")
        assert spec is not None
        assert spec.endpoint_id == str(ep)
        assert spec.fallback is not None
        assert spec.fallback.base_url == "http://mirror"
        # Budget de throttling du fallback (consommé par les appels basculés).
        assert spec.fallback.endpoint_id is not None
        assert spec.fallback.rpm_limit == 100
        assert spec.fallback.max_concurrency == 2

    @pytest.mark.asyncio
    async def test_best_effort_on_error(self) -> None:
        pool = SimpleNamespace(fetchrow=AsyncMock(side_effect=RuntimeError("db down")))
        assert await load_failover(pool, workspace_id=uuid4(), service="llm") is None
