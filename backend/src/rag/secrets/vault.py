from __future__ import annotations

from typing import TYPE_CHECKING, cast

import structlog

if TYPE_CHECKING:
    from harpocrate.models.secret import SecretListResponse
    from harpocrate.models.secret_type import SecretType
    from harpocrate.models.wallet import ApiKeyInfo, WalletInfo

log = structlog.get_logger(__name__)


class HarpocrateVaultClient:
    """Wrapper minimal autour du SDK officiel Harpocrate.

    Le SDK (`harpocrate.VaultClient`) gère l'extraction du dkey depuis le token
    et le déchiffrement local AES-GCM. On expose les opérations consommées
    par le service ag-flow.rag tout en isolant les imports SDK (différés à
    `__init__` pour permettre le chargement du module sans le SDK installé).
    """

    def __init__(self, url: str, token: str) -> None:
        from harpocrate import VaultClient as _SdkClient  # type: ignore[import-not-found]

        self._url = url
        self._sdk = _SdkClient(token=token, base_url=url)

    def get_secret(self, path: str) -> str:
        log.debug("vault.lookup", url=self._url, path=path)
        return cast(str, self._sdk.secrets.get(path))

    def set_secret(self, path: str, value: str) -> None:
        """Crée ou met à jour un secret au path donné (upsert idempotent).

        Tente un `put` (update) d'abord ; si le secret n'existe pas encore
        (`SecretNotFound`), crée via `create`. Toute autre exception
        (ex. permission denied, timeout) est propagée à l'appelant.

        Note : import `SecretNotFound` différé car le SDK peut être absent
        au test-time (le module charge sans lui via TYPE_CHECKING).
        """
        from harpocrate.exceptions import SecretNotFound  # type: ignore[import-not-found]

        log.debug("vault.set", url=self._url, path=path)
        try:
            self._sdk.secrets.put(path, value)
        except SecretNotFound:
            self._sdk.secrets.create(path, value)

    def delete_secret(self, path: str) -> None:
        """Supprime le secret au path donné. Best-effort : pas d'erreur si absent."""
        log.debug("vault.delete", url=self._url, path=path)
        try:
            self._sdk.secrets.delete(path)
        except Exception as e:  # best-effort : log et continue si absent
            log.warning("vault.delete.failed", url=self._url, path=path, error=str(e))

    # ─── M5d : enrichissements API ────────────────────────────────

    def whoami(self) -> ApiKeyInfo:
        """Retourne les infos sur l'API key (succès = auth valide)."""
        return self._sdk.whoami()

    def info(self) -> WalletInfo:
        """Retourne les métadonnées du wallet."""
        return self._sdk.info()

    # ─── M5d : catalogue + listing ────────────────────────────────

    def list_types(
        self,
        q: str | None = None,
        include_deprecated: bool = False,
    ) -> list[SecretType]:
        """Liste les types du catalogue Harpocrate."""
        return self._sdk.types.list(q=q, include_deprecated=include_deprecated)

    def list_secrets(
        self,
        tag: str | None = None,
        name_contains: str | None = None,
        path: str | None = None,
        limit: int = 50,
    ) -> SecretListResponse:
        """Liste les secrets du wallet (sans valeurs)."""
        return self._sdk.secrets.list_secrets(
            tag=tag,
            name_contains=name_contains,
            path=path,
            limit=limit,
        )
