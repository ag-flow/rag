from __future__ import annotations

import time
from typing import Any
from uuid import UUID, uuid4

import structlog
from asyncpg import Connection, UniqueViolationError
from harpocrate.exceptions import VaultHttpError  # type: ignore[import-not-found]

from rag.config import Settings
from rag.schemas.harpocrate_vaults import (
    SecretListItem,
    SecretListResponse,
    SecretTypeSummary,
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultTestConnectionResult,
    VaultUpdateRequest,
    WalletInfoResponse,
)
from rag.secrets.exceptions import (
    HarpocrateDekMissingError,
    VaultNameAlreadyExistsError,
    VaultNotFoundError,
)
from rag.secrets.vault import HarpocrateVaultClient

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
_SELECT_BY_API_KEY_ID = (
    "SELECT id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at "
    "FROM harpocrate_vaults WHERE api_key_id = $1"
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
_UPDATE_VAULT_FULL = (
    "UPDATE harpocrate_vaults SET "
    "label = $2, base_url = $3, probe_path = $4, "
    "updated_at = now() "
    "WHERE id = $1 "
    "RETURNING id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at"
)
_UPDATE_ROTATE_API_KEY = (
    "UPDATE harpocrate_vaults SET "
    "api_key_id = $2, "
    "api_key_encrypted = pgp_sym_encrypt($3::text, $4::text), "
    "updated_at = now() "
    "WHERE id = $1 "
    "RETURNING id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at"
)
_SELECT_DEFAULT_ID = "SELECT id FROM harpocrate_vaults WHERE is_default = true"
_PROMOTE_DEFAULT = (
    "UPDATE harpocrate_vaults SET is_default = true, updated_at = now() "
    "WHERE id = $1 "
    "RETURNING id, name, label, base_url, api_key_id, probe_path, "
    "is_default, created_at, updated_at"
)
_DELETE_VAULT = "DELETE FROM harpocrate_vaults WHERE id = $1"


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

    async def get_by_api_key_id(
        self,
        conn: Connection,
        api_key_id: str,
    ) -> VaultSummary | None:
        row = await conn.fetchrow(_SELECT_BY_API_KEY_ID, api_key_id)
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

    async def update(
        self,
        conn: Connection,
        vault_id: UUID,
        req: VaultUpdateRequest,
    ) -> VaultSummary | None:
        current = await self.get_by_id(conn, vault_id)
        if current is None:
            return None
        fields = req.model_dump(exclude_unset=True)
        label = fields.get("label", current.label)
        base_url = fields.get("base_url", current.base_url)
        # Pour probe_path : si la clé est dans le payload (set explicite),
        # on prend la valeur fournie (qui peut être None après validation
        # Pydantic '' → None). Sinon, on garde la valeur courante. Comme
        # `model_dump(exclude_unset=True)` ne contient la clé que si elle a
        # été explicitement fournie, `.get` avec fallback est équivalent au
        # ternaire `if "probe_path" in fields`.
        probe_path = fields.get("probe_path", current.probe_path)

        row = await conn.fetchrow(
            _UPDATE_VAULT_FULL,
            vault_id,
            label,
            base_url,
            probe_path,
        )
        self._invalidate_caches()
        log.info(
            "vault.updated",
            vault_id=str(vault_id),
            fields_changed=list(fields.keys()),
        )
        return VaultSummary.model_validate(dict(row))

    async def rotate_api_key(
        self,
        conn: Connection,
        vault_id: UUID,
        req: VaultRotateApiKeyRequest,
    ) -> VaultSummary | None:
        dek = self._require_dek()
        previous = await self.get_by_id(conn, vault_id)
        if previous is None:
            return None
        row = await conn.fetchrow(
            _UPDATE_ROTATE_API_KEY,
            vault_id,
            req.api_key_id,
            req.api_key,
            dek,
        )
        self._invalidate_caches()
        log.info(
            "vault.api_key_rotated",
            vault_id=str(vault_id),
            api_key_id_old=previous.api_key_id,
            api_key_id_new=req.api_key_id,
        )
        return VaultSummary.model_validate(dict(row))

    async def set_default(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> VaultSummary | None:
        target = await self.get_by_id(conn, vault_id)
        if target is None:
            return None
        async with conn.transaction():
            previous_id = await conn.fetchval(_SELECT_DEFAULT_ID)
            await conn.execute(_DEMOTE_DEFAULT)
            row = await conn.fetchrow(_PROMOTE_DEFAULT, vault_id)
        self._invalidate_caches()
        log.info(
            "vault.default_changed",
            vault_id_old=str(previous_id) if previous_id else None,
            vault_id_new=str(vault_id),
        )
        return VaultSummary.model_validate(dict(row))

    async def delete(self, conn: Connection, vault_id: UUID) -> bool:
        result = await conn.execute(_DELETE_VAULT, vault_id)
        deleted = result.endswith(" 1")
        if deleted:
            self._invalidate_caches()
            log.info("vault.deleted", vault_id=str(vault_id))
        return deleted

    async def test_connection(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> VaultTestConnectionResult:
        vault = await self.get_by_id(conn, vault_id)
        if vault is None:
            raise VaultNotFoundError(str(vault_id))

        api_key = await self.reveal_api_key(conn, vault_id)
        if api_key is None:
            raise VaultNotFoundError(str(vault_id))

        client = HarpocrateVaultClient(url=vault.base_url, token=api_key)

        # Cas auth-only : pas de probe_path → health_check() via wallet-id
        if vault.probe_path is None:
            try:
                client.health_check()
                return VaultTestConnectionResult(
                    ok=True,
                    detail="auth ok (health_check)",
                    probe_path_used="health_check",
                )
            except Exception as exc:
                status_code = getattr(
                    getattr(exc, "response", None),
                    "status_code",
                    None,
                )
                log.info(
                    "vault.test_connection",
                    vault_id=str(vault_id),
                    ok=False,
                    status_code=status_code,
                    mode="health_check",
                )
                if status_code in (401, 403):
                    return VaultTestConnectionResult(
                        ok=False,
                        detail=f"auth refusée ({status_code})",
                        probe_path_used="health_check",
                    )
                return VaultTestConnectionResult(
                    ok=False,
                    detail=f"erreur SDK : {type(exc).__name__}",
                    probe_path_used="health_check",
                )

        # Cas test bout-en-bout : probe_path renseigné → get_secret
        path = vault.probe_path
        try:
            client.get_secret(path)
            return VaultTestConnectionResult(
                ok=True,
                detail="secret résolu",
                probe_path_used=path,
            )
        except Exception as exc:
            status_code = getattr(
                getattr(exc, "response", None),
                "status_code",
                None,
            )
            log.info(
                "vault.test_connection",
                vault_id=str(vault_id),
                ok=False,
                status_code=status_code,
                probe_path_used=path,
            )
            if status_code in (401, 403):
                return VaultTestConnectionResult(
                    ok=False,
                    detail=f"auth refusée ({status_code})",
                    probe_path_used=path,
                )
            if status_code == 404:
                return VaultTestConnectionResult(
                    ok=False,
                    detail=f"probe_path '{path}' introuvable",
                    probe_path_used=path,
                )
            return VaultTestConnectionResult(
                ok=False,
                detail=f"erreur SDK : {type(exc).__name__}",
                probe_path_used=path,
            )

    async def get_wallet_info(
        self,
        conn: Connection,
        vault_id: UUID,
    ) -> WalletInfoResponse:
        """Retourne les métadonnées du wallet via health_check() + info() + token_info().

        - wallet_id : health_check() → GET /v1/api-keys/{id}/wallet-id (200 si auth valide)
        - wallet_name : info() → GET /v1/wallets/{wallet_id}
        - api_key_id, permissions, expires_at : token_info() (lecture locale, sans appel réseau)

        N'appelle plus whoami() qui fait GET /v1/api-keys/{id} et retourne 404
        lorsqu'aucun secret n'a été posé à ce path (comportement normal Harpocrate).

        Raise VaultNotFoundError si vault_id inconnu côté DB.
        Les exceptions SDK (réseau, 401, etc.) sont propagées telles quelles
        pour que le router les map en HTTP.
        """
        vault = await self.get_by_id(conn, vault_id)
        if vault is None:
            raise VaultNotFoundError(str(vault_id))
        api_key = await self.reveal_api_key(conn, vault_id)
        if api_key is None:
            raise VaultNotFoundError(str(vault_id))

        client = HarpocrateVaultClient(url=vault.base_url, token=api_key)
        wallet_id_str = client.health_check()
        tok = client.token_info()

        wallet = None
        try:
            wallet = client.info()
        except VaultHttpError as e:
            if e.status_code == 401:
                log.warning(
                    "vault.info.api_key_not_allowed",
                    vault_id=str(vault_id),
                    url=vault.base_url,
                    status_code=e.status_code,
                )
            else:
                raise

        log.info(
            "vault.info_fetched",
            vault_id=str(vault_id),
            wallet_id=wallet_id_str,
        )

        return WalletInfoResponse(
            wallet_id=UUID(wallet_id_str),
            wallet_name=getattr(wallet, "name", None) if wallet is not None else None,
            api_key_id=str(tok.api_key_id),
            permissions=tok.permission_names,
            api_key_expires_at=tok.expires_at_dt,
        )

    async def list_types(
        self,
        conn: Connection,
        vault_id: UUID,
        *,
        q: str | None = None,
        include_deprecated: bool = False,
    ) -> list[SecretTypeSummary]:
        """Relais sur client.types.list() avec mapping en SecretTypeSummary.

        Raise VaultNotFoundError si vault_id inconnu.
        """
        vault = await self.get_by_id(conn, vault_id)
        if vault is None:
            raise VaultNotFoundError(str(vault_id))
        api_key = await self.reveal_api_key(conn, vault_id)
        if api_key is None:
            raise VaultNotFoundError(str(vault_id))

        client = HarpocrateVaultClient(url=vault.base_url, token=api_key)
        types_sdk = client.list_types(q=q, include_deprecated=include_deprecated)
        result = [
            SecretTypeSummary(
                type_uuid=getattr(t, "type_uuid", None) or t.id,
                type=t.type,
                sous_type=getattr(t, "sous_type", None),
                label=getattr(t, "label", "") or "",
                deprecated=bool(getattr(t, "deprecated", False)),
            )
            for t in types_sdk
        ]
        log.info(
            "vault.types_listed",
            vault_id=str(vault_id),
            count=len(result),
        )
        return result

    async def list_wallet_secrets(
        self,
        conn: Connection,
        vault_id: UUID,
        *,
        path: str | None = None,
        name_contains: str | None = None,
        tag: str | None = None,
        limit: int = 50,
    ) -> SecretListResponse:
        """Relais sur client.secrets.list_secrets() avec mapping.

        Raise VaultNotFoundError si vault_id inconnu.
        """
        vault = await self.get_by_id(conn, vault_id)
        if vault is None:
            raise VaultNotFoundError(str(vault_id))
        api_key = await self.reveal_api_key(conn, vault_id)
        if api_key is None:
            raise VaultNotFoundError(str(vault_id))

        client = HarpocrateVaultClient(url=vault.base_url, token=api_key)
        sdk_resp = client.list_secrets(
            tag=tag,
            name_contains=name_contains,
            path=path,
            limit=limit,
        )
        items = [
            SecretListItem(
                id=s.id,
                name=s.name,
                description=getattr(s, "description", None),
                is_placeholder=bool(getattr(s, "is_placeholder", False)),
                tags=list(getattr(s, "tags", []) or []),
            )
            for s in getattr(sdk_resp, "secrets", [])
        ]
        log.info(
            "vault.secrets_listed",
            vault_id=str(vault_id),
            count=len(items),
            path=path,
        )
        return SecretListResponse(
            secrets=items,
            next_cursor=getattr(sdk_resp, "next_cursor", None),
        )

    async def write_secret(
        self,
        conn: Connection,
        *,
        vault_name: str,
        path: str,
        value: str,
    ) -> None:
        """Écrit un secret dans le coffre désigné. Upsert idempotent.

        Raise :
            VaultNotFoundError si le coffre n'existe pas en DB.
            HarpocrateWriteFailed sur échec côté Harpocrate.
        """
        vault = await self.get_by_name(conn, vault_name)
        if vault is None:
            raise VaultNotFoundError(vault_name)
        clear_api_key = await self.reveal_api_key(conn, vault.id)
        if clear_api_key is None:
            raise VaultNotFoundError(vault_name)
        client = HarpocrateVaultClient(url=str(vault.base_url), token=clear_api_key)
        try:
            client.set_secret(path, value)
        except Exception as e:
            log.error("vault.write.failed", vault=vault_name, path=path, error=str(e))
            from rag.api.errors import HarpocrateWriteFailed

            raise HarpocrateWriteFailed(str(e)) from e

    async def delete_secret(
        self,
        conn: Connection,
        *,
        vault_name: str,
        path: str,
    ) -> None:
        """Supprime un secret du coffre. Best-effort : log si fail, ne lève pas."""
        vault = await self.get_by_name(conn, vault_name)
        if vault is None:
            log.warning("vault.delete.skipped.no_vault", vault=vault_name, path=path)
            return
        clear_api_key = await self.reveal_api_key(conn, vault.id)
        if clear_api_key is None:
            log.warning("vault.delete.skipped.no_api_key", vault=vault_name)
            return
        try:
            client = HarpocrateVaultClient(url=str(vault.base_url), token=clear_api_key)
            client.delete_secret(path)
        except Exception as e:
            log.warning("vault.delete.failed", vault=vault_name, path=path, error=str(e))

    def _invalidate_caches(self) -> None:
        self._default_cache = None
        if self._client_provider is not None:
            self._client_provider.invalidate()
