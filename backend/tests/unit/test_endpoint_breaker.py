"""Machine à états du circuit breaker in-process par (endpoint, service) —
lot 2 de l'enabler fallback (f94bfd84) : fermé → ouvert après N échecs
consécutifs → half-open après cooldown → refermé au premier succès."""

from __future__ import annotations

from rag.services.endpoint_breaker import EndpointBreakerRegistry

_EP = "ep-1"


class _Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def _registry() -> tuple[EndpointBreakerRegistry, _Clock]:
    clock = _Clock()
    return EndpointBreakerRegistry(clock=clock), clock


def _fail(reg: EndpointBreakerRegistry, n: int = 1) -> None:
    for _ in range(n):
        reg.record_failure(_EP, "rerank", failure_threshold=3, cooldown_seconds=60)


class TestBreakerStateMachine:
    def test_closed_by_default(self) -> None:
        reg, _ = _registry()
        assert reg.target(_EP, "rerank") == "primary"
        assert reg.state(_EP, "rerank") == "closed"

    def test_opens_after_threshold_consecutive_failures(self) -> None:
        reg, _ = _registry()
        _fail(reg, 2)
        assert reg.target(_EP, "rerank") == "primary"
        _fail(reg, 1)
        assert reg.state(_EP, "rerank") == "open"
        assert reg.target(_EP, "rerank") == "fallback"

    def test_success_resets_consecutive_count(self) -> None:
        reg, _ = _registry()
        _fail(reg, 2)
        reg.record_success(_EP, "rerank")
        _fail(reg, 2)
        assert reg.state(_EP, "rerank") == "closed"

    def test_half_open_after_cooldown_probes_primary(self) -> None:
        reg, clock = _registry()
        _fail(reg, 3)
        assert reg.target(_EP, "rerank") == "fallback"
        clock.now += 61
        assert reg.target(_EP, "rerank") == "primary"
        assert reg.state(_EP, "rerank") == "half_open"

    def test_half_open_success_closes(self) -> None:
        reg, clock = _registry()
        _fail(reg, 3)
        clock.now += 61
        reg.target(_EP, "rerank")
        reg.record_success(_EP, "rerank")
        assert reg.state(_EP, "rerank") == "closed"
        assert reg.target(_EP, "rerank") == "primary"

    def test_half_open_failure_reopens_for_full_cooldown(self) -> None:
        reg, clock = _registry()
        _fail(reg, 3)
        clock.now += 61
        reg.target(_EP, "rerank")
        _fail(reg, 1)
        assert reg.state(_EP, "rerank") == "open"
        clock.now += 59
        assert reg.target(_EP, "rerank") == "fallback"
        clock.now += 2
        assert reg.target(_EP, "rerank") == "primary"

    def test_services_are_independent(self) -> None:
        reg, _ = _registry()
        _fail(reg, 3)
        assert reg.target(_EP, "rerank") == "fallback"
        assert reg.target(_EP, "vectorization") == "primary"
        assert reg.target("ep-2", "rerank") == "primary"

    def test_snapshot_exposes_health_per_service(self) -> None:
        reg, _ = _registry()
        _fail(reg, 3)
        snap = reg.snapshot(_EP)
        assert snap["rerank"] == "open"
        assert snap.get("vectorization", "closed") == "closed"
