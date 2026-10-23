"""Ce que partagent la création (« Connecter ») et le remplacement de clé
(« Reconnecter ») d'un coffre par le parcours Harpocrate : raison d'échec sûre,
empreintes, appel du SDK hors de la boucle, issue d'un retour."""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

import httpx
import structlog
from harpocrate.exceptions import ConnectError  # type: ignore[import-untyped]

from rag.schemas.harpocrate_vaults import VaultSummary

log = structlog.get_logger(__name__)

# Durée de vie d'une demande côté Harpocrate (contrat §3) : au-delà, le
# request_uri est mort et l'état gardé ici ne sert plus à rien. Reprise pour
# l'attente de confirmation d'un changement de wallet : une clé obtenue ne
# reste pas en base, même chiffrée, plus longtemps que la demande qui l'a amenée.
REQUEST_TTL_MINUTES = 15

PURGE_EXPIRED = "DELETE FROM harpocrate_connect_requests WHERE expires_at < now()"


class ConnectFlowError(Exception):
    """Échec du parcours, avec une raison sûre à montrer à l'admin.

    `reason` est un code stable, traduit par l'IHM — jamais un message
    provenant de Harpocrate ni un fragment de secret.
    """

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True)
class ConnectOutcome:
    """Issue d'un retour de Harpocrate.

    - `created` : coffre créé (Connecter) ;
    - `rotated` : clé du coffre remplacée, même wallet (Reconnecter) ;
    - `confirm_wallet` : clé obtenue sur un autre wallet, ou wallet actuel
      invérifiable — rien n'est enregistré avant la confirmation de l'admin.
    """

    kind: Literal["created", "rotated", "confirm_wallet"]
    vault: VaultSummary
    pending_request_id: UUID | None = None
    # Jeton à poser dans la session : seul ce navigateur pourra confirmer.
    confirm_token: str | None = field(default=None, repr=False)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


async def call_harpocrate(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Appel SDK (synchrone) hors de la boucle, erreurs traduites en raison sûre."""
    try:
        return await asyncio.to_thread(func, *args, **kwargs)
    except ConnectError as exc:
        # error_code est un code du contrat (invalid_grant, invalid_client…),
        # jamais un secret : on peut le journaliser.
        log.warning("harpocrate_connect.refused", error_code=exc.error_code)
        # Les deux refus de déclaration sont distingués : l'admin Harpocrate
        # n'a pas la même chose à corriger (application absente ou
        # désactivée, ou URL de retour qui ne correspond pas au caractère près).
        if exc.error_code == "invalid_client":
            raise ConnectFlowError("client_not_declared") from exc
        if exc.error_code == "invalid_redirect_uri":
            raise ConnectFlowError("redirect_uri_not_declared") from exc
        raise ConnectFlowError("exchange_failed") from exc
    except httpx.HTTPError as exc:
        log.warning("harpocrate_connect.unreachable", error_type=type(exc).__name__)
        raise ConnectFlowError("harpocrate_unreachable") from exc
    except (KeyError, ValueError) as exc:
        # Réponse hors contrat (JSON illisible, champ manquant) : on ne
        # journalise que le type, le corps pourrait contenir un secret.
        log.warning("harpocrate_connect.unexpected_response", error_type=type(exc).__name__)
        raise ConnectFlowError("exchange_failed") from exc
