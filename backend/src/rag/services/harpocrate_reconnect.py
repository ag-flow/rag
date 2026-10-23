"""« Reconnecter » un coffre : remplacer sa clé par celle qu'obtient le parcours
« Connecter à Harpocrate » (départ et retour : `harpocrate_connect`).

Le remplacement a le même effet que « Remplacer la clé » (nouvel api_key_id,
nouvelle clé chiffrée par HARPOCRATE_DEK, caches invalidés), sauf quand la clé
obtenue ouvre un AUTRE wallet que la clé actuelle : les références de secrets
existantes pointeraient alors ailleurs, et l'admin doit le confirmer d'abord.
L'ancienne clé n'est pas révoquée par ragflow : c'est l'écran de consentement
de Harpocrate qui propose de révoquer les anciennes clés de ragflow.
"""

from __future__ import annotations

import asyncio
import json
import secrets
from collections.abc import Callable
from typing import Any
from uuid import UUID

import httpx
import structlog
from asyncpg import Connection
from harpocrate.exceptions import HarpocrateError  # type: ignore[import-untyped]

from rag.config import Settings
from rag.schemas.harpocrate_vaults import (
    VaultReconnectPending,
    VaultRotateApiKeyRequest,
    VaultSummary,
)
from rag.secrets.exceptions import HarpocrateDekMissingError
from rag.secrets.vault import HarpocrateVaultClient
from rag.services.harpocrate_connect_common import (
    REQUEST_TTL_MINUTES,
    ConnectFlowError,
    ConnectOutcome,
    sha256_hex,
)
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)

# (url Harpocrate, token) -> wallet_id ouvert par ce token. Synchrone (SDK).
WalletProbe = Callable[[str, str], str]

_HOLD_PENDING_KEY = (
    "UPDATE harpocrate_connect_requests SET "
    "pending_key_encrypted = pgp_sym_encrypt($2::text, $3::text), "
    "previous_wallet_id = $4, pending_wallet_id = $5, confirm_binding_hash = $6, "
    "expires_at = now() + make_interval(mins => $7) "
    "WHERE id = $1"
)
# Les deux requêtes ci-dessous portent les MÊMES clauses de liaison : la demande
# appartient à cet admin ET à ce navigateur, attend une décision, n'a pas
# expiré. Littéraux complets, sans concaténation (ruff S608, convention du dépôt).
_SELECT_PENDING = (
    "SELECT vault_id, vault_name, previous_wallet_id, pending_wallet_id, expires_at "
    "FROM harpocrate_connect_requests "
    "WHERE id = $1 AND confirm_binding_hash = $2 AND owner_id = $3 "
    "AND pending_key_encrypted IS NOT NULL AND resolved_at IS NULL AND expires_at > now()"
)
# Décision atomique : FOR UPDATE dans la CTE sérialise deux confirmations
# concurrentes (double clic) — la seconde relit resolved_at et ne trouve rien.
# La clé est lue AVANT d'être effacée (RETURNING rend les valeurs écrites).
_RESOLVE_PENDING = (
    "WITH target AS (SELECT id, vault_id, "
    "pgp_sym_decrypt(pending_key_encrypted, $4::text)::text AS pending_key "
    "FROM harpocrate_connect_requests "
    "WHERE id = $1 AND confirm_binding_hash = $2 AND owner_id = $3 "
    "AND pending_key_encrypted IS NOT NULL AND resolved_at IS NULL AND expires_at > now() "
    "FOR UPDATE) "
    "UPDATE harpocrate_connect_requests r SET resolved_at = now(), "
    "pending_key_encrypted = NULL FROM target WHERE r.id = target.id "
    "RETURNING target.vault_id, target.pending_key"
)
_ALREADY_RESOLVED = (
    "SELECT 1 FROM harpocrate_connect_requests "
    "WHERE id = $1 AND confirm_binding_hash = $2 AND owner_id = $3 AND resolved_at IS NOT NULL"
)


def _probe_wallet_id(base_url: str, token: str) -> str:
    return HarpocrateVaultClient(url=base_url, token=token).health_check()


class HarpocrateReconnectService:
    def __init__(
        self,
        settings: Settings,
        vaults: HarpocrateVaultsService,
        *,
        wallet_probe: WalletProbe | None = None,
    ) -> None:
        self._settings = settings
        self._vaults = vaults
        # Injectable : les tests simulent le wallet de la clé actuelle sans réseau.
        self._wallet_probe = wallet_probe or _probe_wallet_id

    def _require_dek(self) -> str:
        dek = self._settings.harpocrate_dek
        if dek is None:
            raise HarpocrateDekMissingError("HARPOCRATE_DEK manquant : impossible de chiffrer")
        return dek.get_secret_value()

    async def resolve_obtained_key(
        self, conn: Connection, *, request_id: UUID, vault_id: UUID, result: Any, dek: str
    ) -> ConnectOutcome:
        """Retour d'une reconnexion : remplace la clé, ou la tient en attente
        si le wallet change."""
        vault = await self._vaults.get_by_id(conn, vault_id)
        if vault is None:
            raise ConnectFlowError("state_unknown")
        previous_wallet = await self._resolve_current_wallet_id(conn, vault)
        new_wallet = UUID(str(result.wallet_id))
        if previous_wallet == new_wallet:
            rotated = await self._rotate(conn, vault_id, str(result.api_key_id), result.token)
            return ConnectOutcome(kind="rotated", vault=rotated)
        # Wallet différent OU invérifiable (clé actuelle expirée, révoquée,
        # Harpocrate muet) : on ne devine pas, on demande. Enregistrer d'office
        # sur un wallet inconnu casserait toutes les références de secrets sans
        # que rien ne le signale avant la première résolution ratée.
        confirm = secrets.token_urlsafe(32)
        pending_key = json.dumps({"api_key_id": str(result.api_key_id), "token": result.token})
        await conn.execute(
            _HOLD_PENDING_KEY,
            request_id,
            pending_key,
            dek,
            previous_wallet,
            new_wallet,
            sha256_hex(confirm),
            REQUEST_TTL_MINUTES,
        )
        log.info(
            "harpocrate_reconnect.wallet_confirmation_required",
            vault_id=str(vault_id),
            previous_wallet_id=str(previous_wallet) if previous_wallet else None,
            new_wallet_id=str(new_wallet),
        )
        return ConnectOutcome(
            kind="confirm_wallet", vault=vault, pending_request_id=request_id, confirm_token=confirm
        )

    async def db_get_pending(
        self, conn: Connection, *, request_id: UUID, confirm_token: str | None, owner_id: str
    ) -> VaultReconnectPending:
        """Ce que l'admin doit voir pour décider : coffre et wallets en jeu."""
        if not confirm_token:
            raise ConnectFlowError("state_unknown")
        row = await conn.fetchrow(_SELECT_PENDING, request_id, sha256_hex(confirm_token), owner_id)
        if row is None:
            raise ConnectFlowError("state_unknown")
        return VaultReconnectPending(
            request_id=request_id,
            vault_id=row["vault_id"],
            vault_name=row["vault_name"],
            previous_wallet_id=row["previous_wallet_id"],
            new_wallet_id=row["pending_wallet_id"],
            expires_at=row["expires_at"],
        )

    async def resolve_confirm(
        self, conn: Connection, *, request_id: UUID, confirm_token: str | None, owner_id: str
    ) -> VaultSummary:
        """Changement de wallet confirmé : la clé tenue en attente remplace l'ancienne."""
        dek = self._require_dek()
        # Une transaction : si le remplacement échoue, la décision n'est pas
        # consommée et la clé reste en attente (l'admin peut réessayer).
        async with conn.transaction():
            row = await self._db_take_pending(conn, request_id, confirm_token, owner_id, dek)
            key = json.loads(row["pending_key"])
            vault = await self._rotate(conn, row["vault_id"], key["api_key_id"], key["token"])
        log.info("harpocrate_reconnect.wallet_change_confirmed", vault_id=str(vault.id))
        return vault

    async def resolve_cancel(
        self, conn: Connection, *, request_id: UUID, confirm_token: str | None, owner_id: str
    ) -> None:
        """Changement de wallet refusé : la clé obtenue est oubliée, l'ancienne reste.

        Elle reste valide chez Harpocrate, rattachée à l'application ragflow :
        l'IHM invite à la révoquer là-bas. ragflow ne révoque aucune clé, ni
        l'ancienne ni celle-ci — c'est le rôle de l'écran de Harpocrate.
        """
        row = await self._db_take_pending(
            conn, request_id, confirm_token, owner_id, self._require_dek()
        )
        log.info("harpocrate_reconnect.wallet_change_refused", vault_id=str(row["vault_id"]))

    async def _db_take_pending(
        self,
        conn: Connection,
        request_id: UUID,
        confirm_token: str | None,
        owner_id: str,
        dek: str,
    ) -> Any:
        if not confirm_token:
            raise ConnectFlowError("state_unknown")
        keys = (request_id, sha256_hex(confirm_token), owner_id)
        row = await conn.fetchrow(_RESOLVE_PENDING, *keys, dek)
        if row is None:
            replayed = await conn.fetchval(_ALREADY_RESOLVED, *keys)
            raise ConnectFlowError("already_used" if replayed else "state_unknown")
        return row

    async def _rotate(
        self, conn: Connection, vault_id: UUID, api_key_id: str, token: str
    ) -> VaultSummary:
        # Même chemin que « Remplacer la clé » : chiffrement par la DEK et
        # invalidation des caches (clients et valeurs résolues) au même endroit.
        req = VaultRotateApiKeyRequest(api_key_id=api_key_id, api_key=token)
        vault = await self._vaults.rotate_api_key(conn, vault_id, req)
        if vault is None:
            # Coffre supprimé entre le retour et la confirmation.
            raise ConnectFlowError("state_unknown")
        return vault

    async def _resolve_current_wallet_id(
        self, conn: Connection, vault: VaultSummary
    ) -> UUID | None:
        """Wallet ouvert par la clé ACTUELLE, ou None si elle ne répond plus.

        Repli volontaire : None n'est pas une erreur ici, c'est le cas d'usage
        même de la reconnexion (clé expirée ou révoquée). L'appelant le traite
        comme un wallet différent — confirmation demandée, rien de deviné.
        """
        token = await self._vaults.reveal_api_key(conn, vault.id)
        if token is None:
            return None
        try:
            wallet_id = await asyncio.to_thread(self._wallet_probe, vault.base_url, token)
            return UUID(str(wallet_id))
        except (HarpocrateError, httpx.HTTPError, KeyError, ValueError) as exc:
            # Le type seul : un message d'erreur SDK peut recopier la requête.
            log.info(
                "harpocrate_reconnect.current_wallet_unknown",
                vault_id=str(vault.id),
                error_type=type(exc).__name__,
            )
            return None
