from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

import structlog

if TYPE_CHECKING:
    from rag.secrets.client_provider import HarpocrateClientProvider

log = structlog.get_logger(__name__)


class UnknownAction(ValueError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """L'action déclarative n'est pas reconnue (`env://`, `vault://`)."""


class EnvVarMissing(KeyError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """La variable d'env référencée n'est pas dans `os.environ`."""


class VaultLookupFailed(RuntimeError):  # noqa: N818 — nom imposé par la spec (formalisme déclaratif)
    """Le coffre Harpocrate a refusé ou n'a pas trouvé le secret."""


@dataclass(frozen=True)
class ParsedRef:
    action: str
    api_key_id: str | None
    path: str


_ENV_RE = re.compile(r"^\$\{env://([^}]+)\}$")
_VAULT_RE = re.compile(r"^\$\{vault://([^:}]+):([^}]+)\}$")
_GENERIC_RE = re.compile(r"^\$\{([a-zA-Z][a-zA-Z0-9_-]*)://.*\}$")


def parse_ref(value: str) -> ParsedRef | None:
    """Parse une référence déclarative `${action://...}`.

    Retourne `None` si `value` n'est pas une référence (valeur littérale).
    Lève `UnknownAction` si la chaîne ressemble à une référence mais l'action
    n'est pas supportée.
    """
    if "${" not in value:
        return None

    if m := _ENV_RE.match(value):
        return ParsedRef(action="env", api_key_id=None, path=m.group(1))

    if m := _VAULT_RE.match(value):
        return ParsedRef(action="vault", api_key_id=m.group(1), path=m.group(2))

    if m := _GENERIC_RE.match(value):
        raise UnknownAction(f"Unknown declarative action: {m.group(1)!r}")

    return None


class VaultClient(Protocol):
    """Interface attendue d'un client Harpocrate (pour mocker en tests)."""

    def get_secret(self, path: str) -> str: ...


@dataclass
class _CacheEntry:
    value: str
    expires_at: float


class SecretResolver:
    """Résolveur de références déclaratives avec cache RAM TTL et invalidation.

    - Valeurs littérales : retournées telles quelles.
    - `${env://VAR}` : `os.environ[VAR]` (fail fast si absent, jamais caché).
    - `${vault://id:path}` : appel au `VaultClient` correspondant, cache TTL.
    - `cache_ttl=0` → pas de cache (utile pour tests).
    - `invalidate(ref)` → supprime l'entrée cachée pour `ref` (silencieux si absente).
    - `clear_cache()` → vide tout.
    - `resolve_with_retry(ref)` → invalide + retry une fois sur 401.
    """

    def __init__(
        self,
        harpocrate_clients: dict[str, VaultClient] | None = None,
        *,
        client_provider: HarpocrateClientProvider | None = None,
        cache_ttl: int = 300,
    ) -> None:
        if (harpocrate_clients is None) == (client_provider is None):
            raise ValueError(
                "SecretResolver requiert EXACTEMENT un de (harpocrate_clients, client_provider)"
            )
        self._clients = harpocrate_clients
        self._provider = client_provider
        self._cache_ttl = cache_ttl
        self._cache: dict[str, _CacheEntry] = {}

    async def resolve(self, value: str) -> str:
        ref = parse_ref(value)
        if ref is None:
            return value

        if ref.action == "env":
            try:
                return os.environ[ref.path]
            except KeyError as e:
                raise EnvVarMissing(f"Environment variable not set: {ref.path}") from e

        if ref.action == "vault":
            return await self._vault_lookup_cached(value, ref.api_key_id, ref.path)

        raise UnknownAction(f"Unhandled action: {ref.action}")

    async def resolve_with_retry(self, value: str) -> str:
        """Comme `resolve`, mais bypass cache + retente une fois sur 401.

        Force une validation fraîche contre le coffre (invalidation préalable)
        afin qu'un secret révoqué côté Harpocrate soit détecté immédiatement.
        Sur `PermissionError`/`VaultLookupFailed`, retente une seule fois.
        """
        self.invalidate(value)
        try:
            return await self.resolve(value)
        except (PermissionError, VaultLookupFailed) as e:
            log.warning("vault.retry_after_401", ref=value, error=str(e))
            self.invalidate(value)
            if self._provider is not None:
                # Force le provider à recharger depuis la DB (un coffre peut avoir
                # été rotaté/recréé entre temps).
                self._provider.invalidate()
            try:
                return await self.resolve(value)
            except (PermissionError, KeyError) as e2:
                raise VaultLookupFailed(f"Retry after 401 failed for {value!r}") from e2

    def invalidate(self, value: str) -> None:
        """Supprime l'entrée cachée pour `value` (silencieux si absente)."""
        self._cache.pop(value, None)

    def clear_cache(self) -> None:
        """Vide entièrement le cache."""
        self._cache.clear()

    async def _vault_lookup_cached(self, raw_ref: str, api_key_id: str | None, path: str) -> str:
        now = time.monotonic()
        if self._cache_ttl > 0:
            entry = self._cache.get(raw_ref)
            if entry is not None and entry.expires_at > now:
                return entry.value

        if api_key_id is None:
            raise UnknownAction("vault:// requires an api_key_id")

        # Récupère le client soit via provider (DB-live) soit via dict legacy.
        if self._provider is not None:
            try:
                client: VaultClient = await self._provider.get_client(api_key_id)
            except Exception as exc:
                raise VaultLookupFailed(
                    f"No Harpocrate client for unknown api_key_id={api_key_id!r}"
                ) from exc
        else:
            client = self._clients.get(api_key_id) if self._clients else None  # type: ignore[assignment]
            if client is None:
                raise VaultLookupFailed(
                    f"No Harpocrate client configured for unknown api_key_id={api_key_id!r}"
                )

        try:
            value = client.get_secret(path)
        except PermissionError as e:
            raise VaultLookupFailed(f"401 on {raw_ref!r}") from e

        if self._cache_ttl > 0:
            self._cache[raw_ref] = _CacheEntry(value=value, expires_at=now + self._cache_ttl)
        return value
