from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, cast
from uuid import UUID

import structlog

if TYPE_CHECKING:
    from harpocrate.models.secret import SecretListResponse
    from harpocrate.models.secret_type import SecretType
    from harpocrate.models.wallet import WalletInfo

log = structlog.get_logger(__name__)


@dataclass(frozen=True)
class TokenInfo:
    """Informations extraites du token sans appel réseau."""

    api_key_id: UUID
    permissions: int
    expires_at: int  # timestamp Unix, 0 = pas d'expiration

    @property
    def permission_names(self) -> list[str]:
        """Noms lisibles des permissions (bitmap → liste)."""
        bits = {
            0x01: "read",
            0x02: "write",
            0x04: "add",
            0x08: "remove",
            0x10: "init",
            0x20: "share",
        }
        return [name for bit, name in bits.items() if self.permissions & bit]

    @property
    def expires_at_dt(self) -> datetime | None:
        """Expiration en datetime UTC, ou None si pas d'expiration."""
        if self.expires_at == 0:
            return None
        return datetime.fromtimestamp(self.expires_at, tz=UTC)


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

    def health_check(self) -> str:
        """Vérifie que l'auth est valide en lisant l'endpoint wallet-id.

        Retourne le wallet_id (UUID str). Lève si l'auth est invalide ou le serveur
        inaccessible.

        N'utilise PAS whoami() qui fait GET /v1/api-keys/{id} et retourne 404
        lorsqu'aucun secret n'a été posé à ce path — ce comportement Harpocrate
        est normal et ne signifie pas que l'auth est invalide.
        """
        log.debug("vault.health_check", url=self._url)
        parsed = self._sdk._parsed
        data = self._sdk._http.get(f"/v1/api-keys/{parsed.api_key_id}/wallet-id")
        return str(data["wallet_id"])

    def token_info(self) -> TokenInfo:
        """Retourne les informations du token sans appel réseau.

        Lit les champs api_key_id, permissions et expires_at depuis le token
        déjà parsé lors de l'initialisation du SDK.
        """
        parsed = self._sdk._parsed
        return TokenInfo(
            api_key_id=parsed.api_key_id,
            permissions=parsed.permissions,
            expires_at=parsed.exp,
        )

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
