from __future__ import annotations

from typing import cast

import structlog

log = structlog.get_logger(__name__)


class HarpocrateVaultClient:
    """Wrapper minimal autour du SDK officiel Harpocrate.

    Le SDK (`harpocrate.VaultClient`) gère l'extraction du dkey depuis le token
    et le déchiffrement local AES-GCM. On expose une interface `get_secret(path)`
    conforme au protocole `VaultClient` consommé par `SecretResolver`.

    L'import du SDK est **différé à `__init__`** afin que ce module se charge
    sans erreur même si le SDK n'est pas installé (cas du dev Windows). L'erreur
    est levée seulement quand on tente d'utiliser le client — fail fast au
    runtime, pas à l'import.

    Depuis SDK 0.6.0 : l'API a migré vers un sous-client `client.secrets.get(name)`
    au lieu de `client.get_secret(path)` direct. Ce wrapper conserve la même
    interface publique (`get_secret`) pour stabilité côté SecretResolver.
    """

    def __init__(self, url: str, token: str) -> None:
        from harpocrate import VaultClient as _SdkClient  # type: ignore[import-not-found]

        self._url = url
        # SDK signature : VaultClient(token, base_url, wallet_key_cache_ttl=600, timeout=30.0)
        self._sdk = _SdkClient(token=token, base_url=url)

    def get_secret(self, path: str) -> str:
        log.debug("vault.lookup", url=self._url, path=path)
        return cast(str, self._sdk.secrets.get(path))
