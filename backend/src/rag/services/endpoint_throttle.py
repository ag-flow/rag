"""Throttling in-process par (endpoint, service) — enabler docflow a7e2ec90.

Application effective des limites configurées sur l'endpoint (migration 087 :
rpm/tpm ; migration 091 : max_concurrency), **agrégée cross-workspace** : la
clé est `(endpoint_id, service)` — tous les workspaces qui partagent un
endpoint consomment le même budget, car la limite protège le fournisseur.

Trois mécanismes composables, tous optionnels (None = désactivé) :
- `max_concurrency` : sémaphore asyncio — borne les appels parallèles ;
- `rpm_limit`       : fenêtre glissante de 60 s sur le nombre d'appels ;
- `tpm_limit`       : fenêtre glissante de 60 s sur les tokens estimés.

Le dépassement ATTEND (asyncio.sleep jusqu'à libération de la fenêtre), il ne
rejette pas : l'appelant ne voit qu'une latence. Une requête dont l'estimation
dépasse à elle seule le budget passe quand la fenêtre est vide (sinon blocage
infini). État en mémoire du process (limite MVP assumée, comme le circuit
breaker fallback) ; `clock`/`sleep` injectables pour les tests.
"""

from __future__ import annotations

import asyncio
import time
from collections import deque
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

import structlog

log = structlog.get_logger(__name__)

_WINDOW_SECONDS = 60.0

Service = str  # "vectorization" | "rerank" | "llm"


class _ServiceThrottle:
    def __init__(self) -> None:
        self.calls: deque[tuple[float, int]] = deque()  # (horodatage, tokens)
        self.semaphore: asyncio.Semaphore | None = None
        self.semaphore_size: int | None = None

    def get_semaphore(self, max_concurrency: int) -> asyncio.Semaphore:
        # Recréé si la limite configurée a changé depuis le dernier appel.
        if self.semaphore is None or self.semaphore_size != max_concurrency:
            self.semaphore = asyncio.Semaphore(max_concurrency)
            self.semaphore_size = max_concurrency
        return self.semaphore


class EndpointThrottleRegistry:
    """Fenêtres et sémaphores du process, clé (endpoint_id, service)."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._states: dict[tuple[str, Service], _ServiceThrottle] = {}

    def _get(self, endpoint_id: str, service: Service) -> _ServiceThrottle:
        return self._states.setdefault((endpoint_id, service), _ServiceThrottle())

    def _prune(self, st: _ServiceThrottle) -> None:
        horizon = self._clock() - _WINDOW_SECONDS
        while st.calls and st.calls[0][0] <= horizon:
            st.calls.popleft()

    def _budget_delay(
        self, st: _ServiceThrottle, *, rpm_limit: int | None, tpm_limit: int | None, tokens: int
    ) -> float:
        """0 si l'appel passe maintenant, sinon délai jusqu'à la prochaine
        libération de fenêtre."""
        self._prune(st)
        rpm_ok = rpm_limit is None or len(st.calls) < rpm_limit
        used = sum(t for _, t in st.calls)
        tpm_ok = tpm_limit is None or used + tokens <= tpm_limit or not st.calls
        if rpm_ok and tpm_ok:
            return 0.0
        oldest = st.calls[0][0]
        return max(oldest + _WINDOW_SECONDS - self._clock(), 0.01)

    @asynccontextmanager
    async def slot(
        self,
        endpoint_id: str,
        service: Service,
        *,
        max_concurrency: int | None = None,
        rpm_limit: int | None = None,
        tpm_limit: int | None = None,
        tokens: int = 0,
    ) -> AsyncIterator[None]:
        """Réserve un créneau d'appel : attend le budget rpm/tpm puis tient un
        jeton du sémaphore le temps de l'appel."""
        st = self._get(endpoint_id, service)
        if rpm_limit is not None or tpm_limit is not None:
            waited = 0.0
            while True:
                delay = self._budget_delay(
                    st, rpm_limit=rpm_limit, tpm_limit=tpm_limit, tokens=tokens
                )
                if delay <= 0:
                    break
                waited += delay
                await self._sleep(delay)
            if waited:
                log.info(
                    "endpoint_throttle.waited",
                    endpoint_id=endpoint_id,
                    service=service,
                    waited_seconds=round(waited, 2),
                )
            st.calls.append((self._clock(), tokens))
        if max_concurrency is not None:
            async with st.get_semaphore(max_concurrency):
                yield
        else:
            yield


def estimate_tokens(*texts: str) -> int:
    """Estimation heuristique (≈ 4 caractères / token) pour le budget TPM."""
    return sum(len(t) for t in texts) // 4


# Singleton du process — tous les points d'appel partagent les fenêtres.
_registry = EndpointThrottleRegistry()


def get_throttle_registry() -> EndpointThrottleRegistry:
    return _registry
