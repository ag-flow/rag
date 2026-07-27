"""Circuit breaker in-process par (endpoint, service) — fallback d'endpoint.

Détection d'indisponibilité d'un service d'endpoint (lot 2 de l'enabler
docflow f94bfd84) : fermé → `failure_threshold` échecs consécutifs → **ouvert**
pendant `cooldown_seconds` (les appels vont au fallback) → **half-open** :
l'appel suivant teste le primaire ; succès → fermé (retour automatique),
échec → ré-ouvert pour un cooldown complet.

Seuls les échecs d'indisponibilité comptent (connexion refusée, timeout, 5xx) ;
les 429 relèvent des règles rpm/tpm et les 4xx de configuration remontent en
erreur explicite — c'est au point d'appel de filtrer avant `record_failure`.

État en mémoire du process (limite MVP assumée : plusieurs workers = compteurs
indépendants). `clock` injectable pour les tests ; structlog à chaque
transition d'état.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass

import structlog

log = structlog.get_logger(__name__)

Service = str  # "vectorization" | "rerank" | "llm"
Target = str  # "primary" | "fallback"


@dataclass
class _BreakerState:
    state: str = "closed"  # closed | open | half_open
    failures: int = 0
    open_until: float = 0.0  # horloge monotone


class EndpointBreakerRegistry:
    """État des breakers du process, clé (endpoint_id, service)."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._states: dict[tuple[str, Service], _BreakerState] = {}

    def _get(self, endpoint_id: str, service: Service) -> _BreakerState:
        return self._states.setdefault((endpoint_id, service), _BreakerState())

    def _transition(self, st: _BreakerState, endpoint_id: str, service: Service, to: str) -> None:
        log.info(
            "endpoint_breaker.transition",
            endpoint_id=endpoint_id,
            service=service,
            from_state=st.state,
            to_state=to,
        )
        st.state = to

    def target(self, endpoint_id: str, service: Service) -> Target:
        """Cible de l'appel qui démarre. Fait la transition open → half_open à
        l'expiration du cooldown : l'appel half-open teste le primaire."""
        st = self._get(endpoint_id, service)
        if st.state == "open":
            if self._clock() >= st.open_until:
                self._transition(st, endpoint_id, service, "half_open")
                return "primary"
            return "fallback"
        return "primary"

    def state(self, endpoint_id: str, service: Service) -> str:
        return self._get(endpoint_id, service).state

    def record_success(self, endpoint_id: str, service: Service) -> None:
        st = self._get(endpoint_id, service)
        if st.state != "closed":
            self._transition(st, endpoint_id, service, "closed")
        st.failures = 0

    def record_failure(
        self,
        endpoint_id: str,
        service: Service,
        *,
        failure_threshold: int,
        cooldown_seconds: int,
    ) -> None:
        """Comptabilise un échec QUALIFIÉ (indisponibilité — filtré en amont)."""
        st = self._get(endpoint_id, service)
        if st.state == "half_open":
            st.open_until = self._clock() + cooldown_seconds
            self._transition(st, endpoint_id, service, "open")
            return
        st.failures += 1
        if st.state == "closed" and st.failures >= failure_threshold:
            st.open_until = self._clock() + cooldown_seconds
            self._transition(st, endpoint_id, service, "open")

    def snapshot(self, endpoint_id: str) -> dict[Service, str]:
        """État par service de cet endpoint (health du lot 3) — les services
        jamais sollicités sont absents (= closed)."""
        return {
            service: st.state for (ep, service), st in self._states.items() if ep == endpoint_id
        }


# Singleton du process — les points d'appel (indexer, rerank, llm) partagent
# le même état par (endpoint, service).
_registry = EndpointBreakerRegistry()


def get_breaker_registry() -> EndpointBreakerRegistry:
    return _registry
