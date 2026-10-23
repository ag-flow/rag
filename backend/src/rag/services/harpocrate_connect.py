"""Parcours « Connecter à Harpocrate » : créer un coffre — ou en remplacer la
clé (« Reconnecter », `harpocrate_reconnect`) — sans copier-coller de clé.

Contrat Harpocrate (docflow `harpocrate`, 3d5af640) : dépôt PAR + PKCE, retour
du navigateur avec `code` + `state`, échange par le backend, descellement de la
clé. Le SDK ≥ 0.8.0 (`harpocrate.connect`) fait le protocole ; ce module tient
ce que le contrat laisse à l'application :
- garder l'état (code_verifier, clé privée éphémère) CÔTÉ SERVEUR, chiffré ;
- lier le `state` à la session de l'admin qui a lancé le parcours ;
- consommer la demande une seule fois ;
- enregistrer la clé obtenue par le mécanisme existant des coffres
  (création, ou remplacement de clé pour une reconnexion).
Rien de ce qui est secret (token, code, code_verifier, scellé) n'est journalisé
ni renvoyé au navigateur.
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

import structlog
from asyncpg import Connection
from harpocrate import connect as harpocrate_connect  # type: ignore[import-untyped]

from rag.config import Settings
from rag.schemas.harpocrate_vaults import VaultCreateRequest, VaultIdentity, VaultSummary
from rag.secrets.exceptions import HarpocrateDekMissingError, VaultNameAlreadyExistsError
from rag.services.harpocrate_connect_common import (
    PURGE_EXPIRED,
    REQUEST_TTL_MINUTES,
    ConnectFlowError,
    ConnectOutcome,
    call_harpocrate,
    sha256_hex,
)
from rag.services.harpocrate_reconnect import HarpocrateReconnectService, WalletProbe
from rag.services.harpocrate_vaults import HarpocrateVaultsService

log = structlog.get_logger(__name__)

# Permissions demandées pour la clé (bitmap Harpocrate : read=1, add=2, init=4,
# write=8, remove=16, share=32). ragflow lit les secrets, mais aussi en crée,
# en remplace et en supprime (clés providers, clés SSH, secrets de webhooks) :
# read+add+write+remove = 27, décision architecte du 2026-10-20. Ni init ni
# share : ragflow n'initialise ni ne partage de wallet. L'utilisateur peut
# encore réduire côté Harpocrate, jamais élargir.
CONNECT_PERMISSIONS = 1 | 2 | 8 | 16
# Durée de vie demandée pour la clé : bornée plutôt qu'illimitée, l'écran des
# coffres alerte déjà avant l'expiration et « Remplacer la clé » la renouvelle.
CONNECT_TTL_DAYS = 365
_NAME_TAKEN = "SELECT 1 FROM harpocrate_vaults WHERE name = $1"
_INSERT_REQUEST = (
    "INSERT INTO harpocrate_connect_requests "
    "(state_hash, binding_hash, owner_id, vault_name, vault_label, base_url, "
    "is_default, connect_state_encrypted, expires_at, vault_id) "
    "VALUES ($1, $2, $3, $4, $5, $6, $7, pgp_sym_encrypt($8::text, $9::text), "
    "now() + make_interval(mins => $10), $11)"
)
# Consommation atomique : un seul retour peut gagner, même en parallèle (double
# clic, rafraîchissement). La liaison session + owner est dans le WHERE : un
# state présenté par un autre navigateur ou un autre admin ne trouve rien.
_CONSUME_REQUEST = (
    "UPDATE harpocrate_connect_requests SET consumed_at = now() "
    "WHERE state_hash = $1 AND binding_hash = $2 AND owner_id = $3 "
    "AND consumed_at IS NULL AND expires_at > now() "
    "RETURNING id, vault_id, vault_name, vault_label, base_url, is_default, "
    "pgp_sym_decrypt(connect_state_encrypted, $4::text)::text AS connect_state"
)
_ALREADY_CONSUMED = (
    "SELECT 1 FROM harpocrate_connect_requests "
    "WHERE state_hash = $1 AND binding_hash = $2 AND owner_id = $3 "
    "AND consumed_at IS NOT NULL"
)


@dataclass(frozen=True)
class ConnectStart:
    browser_url: str
    # Jeton de liaison à poser dans la session de l'admin : seul ce navigateur
    # pourra conclure la demande.
    binding_token: str = field(repr=False)


def _insecure_allowed() -> bool:
    return os.environ.get("HARPOCRATE_ALLOW_INSECURE", "0") == "1"


class HarpocrateConnectService:
    def __init__(
        self,
        settings: Settings,
        vaults: HarpocrateVaultsService,
        *,
        sdk_start: Callable[..., tuple[str, Any]] = harpocrate_connect.start,
        sdk_finish: Callable[..., Any] = harpocrate_connect.finish,
        wallet_probe: WalletProbe | None = None,
    ) -> None:
        self._settings = settings
        self._vaults = vaults
        # Le SDK est injectable : les tests simulent Harpocrate sans réseau.
        self._sdk_start = sdk_start
        self._sdk_finish = sdk_finish
        self.reconnect = HarpocrateReconnectService(settings, vaults, wallet_probe=wallet_probe)

    def _require_dek(self) -> str:
        dek = self._settings.harpocrate_dek
        if dek is None:
            raise HarpocrateDekMissingError("HARPOCRATE_DEK manquant : impossible de chiffrer")
        return dek.get_secret_value()

    async def resolve_start(
        self,
        conn: Connection,
        *,
        identity: VaultIdentity,
        owner_id: str,
        redirect_uri: str,
    ) -> ConnectStart:
        """Dépose une demande de CRÉATION de coffre et garde son état, chiffré."""
        # Contrôle anticipé du nom : éviter d'envoyer l'admin consentir chez
        # Harpocrate pour un coffre qu'on ne pourra pas créer. La création
        # au retour reste l'arbitre (le nom peut être pris entre-temps).
        self._check_https(identity.base_url)
        if await conn.fetchval(_NAME_TAKEN, identity.name):
            raise ConnectFlowError("name_taken")
        return await self._deposit(
            conn, identity=identity, vault_id=None, owner_id=owner_id, redirect_uri=redirect_uri
        )

    async def resolve_reconnect_start(
        self,
        conn: Connection,
        *,
        vault: VaultSummary,
        owner_id: str,
        redirect_uri: str,
    ) -> ConnectStart:
        """Dépose une demande de REMPLACEMENT de la clé d'un coffre existant.

        Même client_id, même URL de retour et mêmes permissions que la
        création : seule la cible change, portée par la demande (`vault_id`).
        """
        self._check_https(vault.base_url)
        identity = VaultIdentity(
            name=vault.name, label=vault.label, base_url=vault.base_url, is_default=vault.is_default
        )
        return await self._deposit(
            conn, identity=identity, vault_id=vault.id, owner_id=owner_id, redirect_uri=redirect_uri
        )

    @staticmethod
    def _check_https(base_url: str) -> None:
        # Même règle que le SDK (`_check_base_url`), vérifiée ici pour rendre
        # une raison lisible plutôt qu'un ValueError générique.
        if base_url.startswith("http://") and not _insecure_allowed():
            raise ConnectFlowError("https_required")

    async def _deposit(
        self,
        conn: Connection,
        *,
        identity: VaultIdentity,
        vault_id: UUID | None,
        owner_id: str,
        redirect_uri: str,
    ) -> ConnectStart:
        dek = self._require_dek()
        await conn.execute(PURGE_EXPIRED)
        browser_url, pending = await call_harpocrate(
            self._sdk_start,
            identity.base_url,
            self._settings.harpocrate_connect_client_id,
            redirect_uri,
            CONNECT_PERMISSIONS,
            CONNECT_TTL_DAYS,
        )
        binding = secrets.token_urlsafe(32)
        await conn.execute(
            _INSERT_REQUEST,
            sha256_hex(pending.state),
            sha256_hex(binding),
            owner_id,
            identity.name,
            identity.label,
            identity.base_url,
            identity.is_default,
            json.dumps(pending.to_dict()),
            dek,
            REQUEST_TTL_MINUTES,
            vault_id,
        )
        log.info(
            "harpocrate_connect.started",
            vault_name=identity.name,
            owner_id=owner_id,
            mode="create" if vault_id is None else "reconnect",
        )
        return ConnectStart(browser_url=browser_url, binding_token=binding)

    async def resolve_callback(
        self,
        conn: Connection,
        *,
        owner_id: str,
        binding_token: str | None,
        state: str | None,
        code: str | None,
        error: str | None,
    ) -> ConnectOutcome:
        """Conclut une demande : vérifie la liaison, échange, puis crée le
        coffre ou en remplace la clé selon la demande."""
        dek = self._require_dek()
        # Fail closed AVANT tout appel à Harpocrate : sans liaison de session
        # ni state, un tiers pourrait faire enregistrer une clé sur SON wallet.
        if not binding_token or not state:
            raise ConnectFlowError("state_unknown")
        keys = (sha256_hex(state), sha256_hex(binding_token), owner_id)
        row = await conn.fetchrow(_CONSUME_REQUEST, *keys, dek)
        if row is None:
            replayed = await conn.fetchval(_ALREADY_CONSUMED, *keys)
            raise ConnectFlowError("already_used" if replayed else "state_unknown")
        if error is not None:
            # Refus chez Harpocrate (access_denied) : demande consommée, rien
            # créé ni remplacé — l'ancienne clé d'un coffre reconnecté reste.
            log.info("harpocrate_connect.denied", vault_name=row["vault_name"], error=error)
            raise ConnectFlowError("denied")
        if not code:
            raise ConnectFlowError("exchange_failed")
        pending = harpocrate_connect.ConnectState.from_dict(json.loads(row["connect_state"]))
        result = await call_harpocrate(self._sdk_finish, pending, code=code, state=state)
        if row["vault_id"] is None:
            vault = await self._create_vault(conn, row, result, owner_id)
            return ConnectOutcome(kind="created", vault=vault)
        return await self.reconnect.resolve_obtained_key(
            conn, request_id=row["id"], vault_id=row["vault_id"], result=result, dek=dek
        )

    async def _create_vault(
        self, conn: Connection, row: Any, result: Any, owner_id: str
    ) -> VaultSummary:
        request = VaultCreateRequest(
            name=row["vault_name"],
            label=row["vault_label"],
            base_url=row["base_url"],
            is_default=row["is_default"],
            api_key_id=str(result.api_key_id),
            api_key=result.token,
        )
        try:
            vault = await self._vaults.create(conn, request, owner_id=owner_id)
        except VaultNameAlreadyExistsError as exc:
            # La clé obtenue n'est PAS enregistrée : l'IHM le dit explicitement
            # plutôt que de la perdre en silence (elle reste révocable chez
            # Harpocrate, rattachée à l'application ragflow).
            log.warning("harpocrate_connect.name_taken", vault_name=row["vault_name"])
            raise ConnectFlowError("name_taken_key_not_saved") from exc
        log.info(
            "harpocrate_connect.vault_created",
            vault_id=str(vault.id),
            wallet_id=str(result.wallet_id),
            api_key_id=str(result.api_key_id),
        )
        return vault
