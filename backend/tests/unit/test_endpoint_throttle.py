"""Throttling in-process par (endpoint, service) — enabler a7e2ec90 :
sémaphore de concurrence + fenêtres glissantes RPM/TPM, clé cross-workspace
au niveau de l'endpoint. Horloge et sleep injectables."""

from __future__ import annotations

import asyncio

import pytest

from rag.services.endpoint_throttle import EndpointThrottleRegistry

_EP = "ep-1"


class _FakeTime:
    """Horloge virtuelle : sleep avance l'horloge sans attendre réellement."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def _registry() -> tuple[EndpointThrottleRegistry, _FakeTime]:
    ft = _FakeTime()
    return EndpointThrottleRegistry(clock=ft.clock, sleep=ft.sleep), ft


class TestRpmWindow:
    @pytest.mark.asyncio
    async def test_no_limits_is_passthrough(self) -> None:
        reg, ft = _registry()
        async with reg.slot(_EP, "vectorization"):
            pass
        assert ft.slept == []

    @pytest.mark.asyncio
    async def test_waits_when_rpm_exhausted(self) -> None:
        reg, ft = _registry()
        for _ in range(2):
            async with reg.slot(_EP, "vectorization", rpm_limit=2):
                pass
        assert ft.slept == []
        async with reg.slot(_EP, "vectorization", rpm_limit=2):
            pass
        # A dû attendre l'expiration de la fenêtre de 60 s.
        assert len(ft.slept) >= 1
        assert ft.now >= 1060.0

    @pytest.mark.asyncio
    async def test_window_slides(self) -> None:
        reg, ft = _registry()
        async with reg.slot(_EP, "vectorization", rpm_limit=2):
            pass
        ft.now += 61  # la première requête sort de la fenêtre
        async with reg.slot(_EP, "vectorization", rpm_limit=2):
            pass
        async with reg.slot(_EP, "vectorization", rpm_limit=2):
            pass
        assert ft.slept == []


class TestTpmWindow:
    @pytest.mark.asyncio
    async def test_waits_when_token_budget_exhausted(self) -> None:
        reg, ft = _registry()
        async with reg.slot(_EP, "vectorization", tpm_limit=100, tokens=80):
            pass
        async with reg.slot(_EP, "vectorization", tpm_limit=100, tokens=30):
            pass
        assert len(ft.slept) >= 1
        assert ft.now >= 1060.0

    @pytest.mark.asyncio
    async def test_oversized_request_passes_alone(self) -> None:
        # Une requête > budget passe seule (sinon blocage infini) — fenêtre vide.
        reg, ft = _registry()
        async with reg.slot(_EP, "vectorization", tpm_limit=100, tokens=250):
            pass
        assert ft.slept == []


class TestConcurrency:
    @pytest.mark.asyncio
    async def test_semaphore_bounds_parallel_calls(self) -> None:
        reg, _ = _registry()
        active = 0
        peak = 0

        async def call() -> None:
            nonlocal active, peak
            async with reg.slot(_EP, "rerank", max_concurrency=2):
                active += 1
                peak = max(peak, active)
                await asyncio.sleep(0)
                active -= 1

        await asyncio.gather(*(call() for _ in range(6)))
        assert peak <= 2

    @pytest.mark.asyncio
    async def test_keys_are_independent(self) -> None:
        reg, ft = _registry()
        async with reg.slot(_EP, "vectorization", rpm_limit=1):
            pass
        # Autre service, autre endpoint : fenêtres indépendantes.
        async with reg.slot(_EP, "rerank", rpm_limit=1):
            pass
        async with reg.slot("ep-2", "vectorization", rpm_limit=1):
            pass
        assert ft.slept == []
