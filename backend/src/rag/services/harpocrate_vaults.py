from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import structlog
from asyncpg import Connection, UniqueViolationError

from rag.config import Settings
from rag.schemas.harpocrate_vaults import (
    VaultCreateRequest,
    VaultSummary,
)
from rag.secrets.exceptions import (
    HarpocrateDekMissingError,
    VaultNameAlreadyExistsError,
)

log = structlog.get_logger(__name__)

_DEFAULT_CACHE_TTL_SECONDS = 60

# Toutes les requêtes sont des littéraux statiques (pas de f-string) pour
# satisfaire ruff S608 et éviter toute ambiguïté sur la provenance des
# fragments SQL : seuls les paramètres ($1, $2, ...) sont bindés.
_SELECT_ALL = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults ORDER BY created_at"
)
_SELECT_BY_ID = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults WHERE id = $1"
)
_SELECT_BY_NAME = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults WHERE name = $1"
)
_SELECT_DEFAULT = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults WHERE is_default = true"
)
_SELECT_REVEAL = (
    "SELECT pgp_sym_decrypt(api_key_encrypted, $2::text)::text AS api_key "
    "FROM harpocrate_vaults WHERE id = $1"
)
_DEMOTE_DEFAULT = (
    "UPDATE harpocrate_vaults SET is_default = false, updated_at = now() WHERE is_default = true"
)
_INSERT_VAULT = (
    "INSERT INTO harpocrate_vaults "
    "(id, name, label, base_url, api_key_id, api_key_encrypted, "
    "probe_path, is_default) "
    "VALUES ($1, $2, $3, $4, $5, pgp_sym_encrypt($6::text, $7::text), $8, $9) "
    "RETURNING id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at"
)


class HarpocrateVaultsService:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._default_cache: tuple[float, VaultSummary | None] | None = None
        self._client_provider: Any = None

    def bind_client_provider(self, provider: Any) -> None:
        """Lié post-construction par le lifespan pour éviter le cycle d'import."""
        self._client_provider = provider

    def _require_dek(self) -> str:
        dek = self._settings.harpocrate_dek
        if dek is None:
            raise HarpocrateDekMissingError(
                "HARPOCRATE_DEK manquant alors qu'au moins un coffre est requis"
            )
        return dek.get_secret_value()

    # --- Reads ---------------------------------------------------------

    async def list_all(self, conn: Connection) -> list[VaultSummary]:
        rows = await conn.fetch(_SELECT_ALL)
        return [VaultSummary.model_validate(dict(r)) for r in rows]

    async def get_by_id(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> VaultSummary | None:
        row = await conn.fetchrow(_SELECT_BY_ID, vault_id)
        return VaultSummary.model_validate(dict(row)) if row else None

    async def get_by_name(
        self,
        conn: Connection,
        name: str,
    ) -> VaultSummary | None:
        row = await conn.fetchrow(_SELECT_BY_NAME, name)
        return VaultSummary.model_validate(dict(row)) if row else None

    async def get_default(self, conn: Connection) -> VaultSummary | None:
        if self._default_cache is not None:
            ts, value = self._default_cache
            if time.monotonic() - ts < _DEFAULT_CACHE_TTL_SECONDS:
                return value
        row = await conn.fetchrow(_SELECT_DEFAULT)
        value = VaultSummary.model_validate(dict(row)) if row else None
        self._default_cache = (time.monotonic(), value)
        return value

    async def reveal_api_key(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> str | None:
        dek = self._require_dek()
        row = await conn.fetchrow(_SELECT_REVEAL, vault_id, dek)
        return row["api_key"] if row else None

    # --- Writes --------------------------------------------------------

    async def create(
        self,
        conn: Connection,
        req: VaultCreateRequest,
    ) -> VaultSummary:
        dek = self._require_dek()
        vault_id = uuid4()

        if req.is_default:
            await conn.execute(_DEMOTE_DEFAULT)

        try:
            row = await conn.fetchrow(
                _INSERT_VAULT,
                vault_id,
                req.name,
                req.label,
                req.base_url,
                req.api_key_id,
                req.api_key,
                dek,
                req.probe_path,
                req.is_default,
            )
        except UniqueViolationError as exc:
            raise VaultNameAlreadyExistsError(req.name) from exc

        self._invalidate_caches()
        log.info(
            "vault.created",
            vault_id=str(vault_id),
            name=req.name,
            is_default=req.is_default,
        )
        return VaultSummary.model_validate(dict(row))

    def _invalidate_caches(self) -> None:
        self._default_cache = None
        if self._client_provider is not None:
            self._client_provider.invalidate()
