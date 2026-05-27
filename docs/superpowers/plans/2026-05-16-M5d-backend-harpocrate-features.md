# M5d-backend — Exploitation SDK Harpocrate 0.6.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exploiter les features du SDK Harpocrate 0.6.0 dans le backend ag-flow.rag : `whoami()`/`info()`/`types.list()`/`secrets.list_secrets()`. Refactorer `test_connection` pour utiliser `whoami()` à la place du probe heuristique (404=OK). Exposer 3 nouveaux endpoints admin `/info`, `/types`, `/secrets`.

**Architecture:** Wrapper minimal `HarpocrateVaultClient` étendu de 4 méthodes. Service `HarpocrateVaultsService` augmenté de 3 méthodes (`get_wallet_info`, `list_types`, `list_wallet_secrets`) + refactor `test_connection`. Router admin gagne 3 endpoints GET sous `/api/admin/harpocrate-vaults/{vault_id}`. Schemas DTOs : `WalletInfoResponse`, `SecretTypeSummary`, `SecretListItem`, `SecretListResponse`.

**Tech Stack:** Python 3.12 + Pydantic v2 + FastAPI + asyncpg + structlog. SDK Harpocrate 0.6.0 vendoré en source local éditable (`vendor/harpocrate-sdk/`). Spec design : `docs/superpowers/specs/2026-05-16-M5d-backend-harpocrate-features-design.md`.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/src/rag/secrets/vault.py` | **Modify** | +4 méthodes wrapper : `whoami`, `info`, `list_types`, `list_secrets` |
| `backend/src/rag/schemas/harpocrate_vaults.py` | **Modify** | +4 DTOs Pydantic : `WalletInfoResponse`, `SecretTypeSummary`, `SecretListItem`, `SecretListResponse` |
| `backend/src/rag/services/harpocrate_vaults.py` | **Modify** | +3 méthodes service + refactor `test_connection` |
| `backend/src/rag/api/admin_harpocrate_vaults.py` | **Modify** | +3 endpoints GET (`/info`, `/types`, `/secrets`) |
| `backend/tests/unit/schemas/test_harpocrate_vaults_dto.py` | **Modify** | +tests DTOs M5d |
| `backend/tests/integration/test_harpocrate_vaults_service_test_connection.py` | **Modify** | Adapter le test M5c "404 sans probe_path = OK" |
| `backend/tests/integration/test_harpocrate_vaults_service_m5d.py` | **Create** | Tests des 3 nouvelles méthodes service |
| `backend/tests/api/test_admin_harpocrate_vaults_m5d.py` | **Create** | Tests HTTP des 3 nouveaux endpoints |

---

## Task 1: Étendre `HarpocrateVaultClient` (4 méthodes wrapper)

**Files:**
- Modify: `backend/src/rag/secrets/vault.py`

Le wrapper relaye le SDK ; pas de tests dédiés (les tests M5d-T3/T4 valideront via mocks de `HarpocrateVaultClient` au niveau service).

- [ ] **Step 1: Étendre `backend/src/rag/secrets/vault.py`**

Ajouter les imports et les 4 méthodes. Code complet du fichier après modif :

```python
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

    # ─── M5d : enrichissements API ────────────────────────────────

    def whoami(self) -> "ApiKeyInfo":
        """Retourne les infos sur l'API key (succès = auth valide)."""
        return self._sdk.whoami()

    def info(self) -> "WalletInfo":
        """Retourne les métadonnées du wallet."""
        return self._sdk.info()

    # ─── M5d : catalogue + listing ────────────────────────────────

    def list_types(
        self, q: str | None = None, include_deprecated: bool = False,
    ) -> list["SecretType"]:
        """Liste les types du catalogue Harpocrate."""
        return self._sdk.types.list(q=q, include_deprecated=include_deprecated)

    def list_secrets(
        self,
        tag: str | None = None,
        name_contains: str | None = None,
        path: str | None = None,
        limit: int = 50,
    ) -> "SecretListResponse":
        """Liste les secrets du wallet (sans valeurs)."""
        return self._sdk.secrets.list_secrets(
            tag=tag, name_contains=name_contains, path=path, limit=limit,
        )
```

- [ ] **Step 2: Smoke import**

```powershell
cd backend
uv run python -c "from rag.secrets.vault import HarpocrateVaultClient; assert hasattr(HarpocrateVaultClient, 'whoami'); assert hasattr(HarpocrateVaultClient, 'info'); assert hasattr(HarpocrateVaultClient, 'list_types'); assert hasattr(HarpocrateVaultClient, 'list_secrets'); print('OK')"
```

Expected : `OK`.

- [ ] **Step 3: Non-régression**

```powershell
uv run pytest tests/unit/ -q
```

Expected : 316 passed (état post-migration SDK).

- [ ] **Step 4: Ruff**

```powershell
uv run ruff check src/rag/secrets/vault.py
uv run ruff format src/rag/secrets/vault.py
```

- [ ] **Step 5: Commit**

```powershell
cd ..
git add backend/src/rag/secrets/vault.py
git commit -m "feat(M5d): HarpocrateVaultClient +whoami/info/list_types/list_secrets"
```

---

## Task 2: Étendre les schemas Pydantic

**Files:**
- Modify: `backend/src/rag/schemas/harpocrate_vaults.py`
- Modify: `backend/tests/unit/schemas/test_harpocrate_vaults_dto.py`

- [ ] **Step 1: Écrire les tests d'abord (TDD red)**

Ajouter au bas de `backend/tests/unit/schemas/test_harpocrate_vaults_dto.py` :

```python
from datetime import datetime, timezone
from uuid import uuid4

from rag.schemas.harpocrate_vaults import (
    SecretListItem,
    SecretListResponse,
    SecretTypeSummary,
    WalletInfoResponse,
)


def test_wallet_info_response_minimal():
    info = WalletInfoResponse(
        wallet_id=uuid4(),
        wallet_name=None,
        api_key_id="k-001",
        permissions=["read", "write"],
        api_key_expires_at=None,
    )
    assert info.permissions == ["read", "write"]
    assert info.wallet_name is None


def test_wallet_info_response_full():
    expires = datetime(2026, 12, 31, tzinfo=timezone.utc)
    info = WalletInfoResponse(
        wallet_id=uuid4(),
        wallet_name="prod-wallet",
        api_key_id="k-001",
        permissions=["read"],
        api_key_expires_at=expires,
    )
    assert info.api_key_expires_at == expires


def test_secret_type_summary():
    t = SecretTypeSummary(
        type_uuid=uuid4(),
        type="openai_api_key",
        sous_type=None,
        label="OpenAI API key",
        deprecated=False,
    )
    assert t.type == "openai_api_key"
    assert t.deprecated is False


def test_secret_list_item():
    item = SecretListItem(
        id=uuid4(),
        name="anthropic_key",
        description=None,
        is_placeholder=False,
        tags=[],
    )
    assert item.name == "anthropic_key"
    assert item.tags == []


def test_secret_list_response_paginated():
    resp = SecretListResponse(
        secrets=[
            SecretListItem(
                id=uuid4(),
                name="k1",
                description=None,
                is_placeholder=False,
                tags=["env:prod"],
            ),
        ],
        next_cursor="opaque-cursor-1",
    )
    assert len(resp.secrets) == 1
    assert resp.next_cursor == "opaque-cursor-1"


def test_secret_list_response_no_cursor():
    resp = SecretListResponse(secrets=[], next_cursor=None)
    assert resp.next_cursor is None
```

- [ ] **Step 2: Lancer, doit échouer**

```powershell
cd backend
uv run pytest tests/unit/schemas/test_harpocrate_vaults_dto.py -v 2>&1 | tail -15
```

Expected : 5 FAIL (DTOs M5d inexistants).

- [ ] **Step 3: Ajouter les 4 DTOs à `backend/src/rag/schemas/harpocrate_vaults.py`**

Au bas du fichier existant :

```python
class WalletInfoResponse(BaseModel):
    """Métadonnées du coffre Harpocrate (combinaison whoami + info)."""
    wallet_id: UUID
    wallet_name: str | None
    api_key_id: str
    permissions: list[str]
    api_key_expires_at: datetime | None


class SecretTypeSummary(BaseModel):
    """Résumé d'un type du catalogue Harpocrate."""
    type_uuid: UUID
    type: str
    sous_type: str | None
    label: str
    deprecated: bool


class SecretListItem(BaseModel):
    """Résumé d'un secret du wallet (sans valeur)."""
    id: UUID
    name: str
    description: str | None
    is_placeholder: bool
    tags: list[str]


class SecretListResponse(BaseModel):
    """Réponse paginée du listing des secrets."""
    secrets: list[SecretListItem]
    next_cursor: str | None
```

- [ ] **Step 4: Lancer, doit passer**

```powershell
uv run pytest tests/unit/schemas/test_harpocrate_vaults_dto.py -v 2>&1 | tail -10
```

Expected : ~20 PASS (les 15 existants + 5 nouveaux).

- [ ] **Step 5: Ruff**

```powershell
uv run ruff check src/rag/schemas/harpocrate_vaults.py tests/unit/schemas/test_harpocrate_vaults_dto.py
uv run ruff format src/rag/schemas/harpocrate_vaults.py tests/unit/schemas/test_harpocrate_vaults_dto.py
```

- [ ] **Step 6: Commit**

```powershell
cd ..
git add backend/src/rag/schemas/harpocrate_vaults.py backend/tests/unit/schemas/test_harpocrate_vaults_dto.py
git commit -m "feat(M5d): schemas WalletInfoResponse + SecretTypeSummary + SecretList*"
```

---

## Task 3: Service — `get_wallet_info` + refactor `test_connection`

**Files:**
- Modify: `backend/src/rag/services/harpocrate_vaults.py`
- Modify: `backend/tests/integration/test_harpocrate_vaults_service_test_connection.py`
- Create: `backend/tests/integration/test_harpocrate_vaults_service_m5d.py`

- [ ] **Step 1: Adapter le test M5c qui change de sémantique**

Dans `backend/tests/integration/test_harpocrate_vaults_service_test_connection.py`, renommer le test `test_test_connection_404_without_probe_path_is_ok` en `test_test_connection_without_probe_path_uses_whoami` et changer son corps. Nouveau code :

```python
@pytest.mark.asyncio
async def test_test_connection_without_probe_path_uses_whoami(
    session_pool: asyncpg.Pool, monkeypatch,
):
    """probe_path=None : on appelle whoami() au lieu d'un probe sur __probe__."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)  # probe_path default = None
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            # whoami() succès = auth OK
            instance.whoami.return_value = MagicMock(api_key_id="k-001")
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is True
    assert "whoami" in result.detail
    assert result.probe_path_used == "whoami"
```

Ajouter ensuite un test pour le cas 401 :

```python
@pytest.mark.asyncio
async def test_test_connection_whoami_401_returns_ko(
    session_pool: asyncpg.Pool, monkeypatch,
):
    """whoami() sur 401 (api_key invalide) → ok=False."""
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.whoami.side_effect = _FakeSdkError(401)
            mock_client.return_value = instance
            result = await svc.test_connection(conn, seeded.id)
    assert result.ok is False
    assert "auth refusée" in result.detail
    assert result.probe_path_used == "whoami"
```

- [ ] **Step 2: Écrire les tests `get_wallet_info`**

Créer `backend/tests/integration/test_harpocrate_vaults_service_m5d.py` :

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch
from uuid import uuid4

import asyncpg
import pytest

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultCreateRequest
from rag.secrets.exceptions import VaultNotFoundError
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"


def _set_env(monkeypatch) -> None:
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv(
        "RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres"
    )
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv(
        "HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long",
    )


def _create_req(**overrides):
    payload = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    payload.update(overrides)
    return VaultCreateRequest(**payload)


async def _seed(svc, conn, **overrides):
    await conn.execute("DELETE FROM harpocrate_vaults")
    async with conn.transaction():
        return await svc.create(conn, _create_req(**overrides))


@pytest.mark.asyncio
async def test_get_wallet_info_combines_whoami_and_info(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        wallet_id = uuid4()
        expires = datetime(2027, 1, 1, tzinfo=timezone.utc)
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.whoami.return_value = MagicMock(
                api_key_id="k-001",
                permissions=["read", "write"],
                expires_at=expires,
            )
            instance.info.return_value = MagicMock(
                wallet_id=wallet_id,
                name="prod-wallet",
            )
            mock_client.return_value = instance
            result = await svc.get_wallet_info(conn, seeded.id)
    assert result.wallet_id == wallet_id
    assert result.wallet_name == "prod-wallet"
    assert result.api_key_id == "k-001"
    assert result.permissions == ["read", "write"]
    assert result.api_key_expires_at == expires


@pytest.mark.asyncio
async def test_get_wallet_info_raises_when_vault_absent(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        with pytest.raises(VaultNotFoundError):
            await svc.get_wallet_info(conn, uuid4())
```

- [ ] **Step 3: Lancer, doit échouer**

```powershell
cd backend
uv run pytest tests/integration/test_harpocrate_vaults_service_test_connection.py tests/integration/test_harpocrate_vaults_service_m5d.py -v
```

Côté local : SKIPPED (TEST_POSTGRES_PASSWORD absent). C'est attendu.

- [ ] **Step 4: Implémenter dans `backend/src/rag/services/harpocrate_vaults.py`**

Ajouter les imports en haut :

```python
from rag.schemas.harpocrate_vaults import (
    SecretListResponse,
    SecretTypeSummary,
    VaultCreateRequest,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultTestConnectionResult,
    VaultUpdateRequest,
    WalletInfoResponse,
    SecretListItem,
)
```

Remplacer entièrement la méthode `test_connection` par :

```python
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

    # Cas auth-only : pas de probe_path → whoami()
    if vault.probe_path is None:
        try:
            client.whoami()
            return VaultTestConnectionResult(
                ok=True,
                detail="auth ok (whoami)",
                probe_path_used="whoami",
            )
        except Exception as exc:
            status_code = getattr(
                getattr(exc, "response", None), "status_code", None,
            )
            log.info(
                "vault.test_connection",
                vault_id=str(vault_id),
                ok=False,
                status_code=status_code,
                mode="whoami",
            )
            if status_code in (401, 403):
                return VaultTestConnectionResult(
                    ok=False,
                    detail=f"auth refusée ({status_code})",
                    probe_path_used="whoami",
                )
            return VaultTestConnectionResult(
                ok=False,
                detail=f"erreur SDK : {type(exc).__name__}",
                probe_path_used="whoami",
            )

    # Cas test bout-en-bout : probe_path renseigné → get_secret
    path = vault.probe_path
    try:
        client.get_secret(path)
        return VaultTestConnectionResult(
            ok=True, detail="secret résolu", probe_path_used=path,
        )
    except Exception as exc:
        status_code = getattr(
            getattr(exc, "response", None), "status_code", None,
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
```

Ajouter la méthode `get_wallet_info` :

```python
async def get_wallet_info(
    self,
    conn: Connection,
    vault_id: UUID,
) -> WalletInfoResponse:
    """Combine whoami() + info() pour retourner les métadonnées du wallet.

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
    api_key_info = client.whoami()
    wallet = client.info()

    log.info(
        "vault.info_fetched",
        vault_id=str(vault_id),
        wallet_id=str(getattr(wallet, "wallet_id", None) or getattr(wallet, "id", None)),
    )

    return WalletInfoResponse(
        wallet_id=getattr(wallet, "wallet_id", None) or getattr(wallet, "id"),
        wallet_name=getattr(wallet, "name", None),
        api_key_id=getattr(api_key_info, "api_key_id"),
        permissions=list(getattr(api_key_info, "permissions", []) or []),
        api_key_expires_at=getattr(api_key_info, "expires_at", None),
    )
```

Note : `getattr(...)` défensif car les modèles SDK exposent `wallet_id` ou `id` selon les versions ; on accepte les deux conventions.

- [ ] **Step 5: Lancer non-régression unit + collect intégration**

```powershell
uv run pytest tests/unit/ -q
uv run pytest tests/integration/test_harpocrate_vaults_service_test_connection.py tests/integration/test_harpocrate_vaults_service_m5d.py --collect-only -q
```

Expected : unit 316+ passed ; collect montre tous les tests sans ImportError.

- [ ] **Step 6: Ruff**

```powershell
uv run ruff check src/rag/services/harpocrate_vaults.py tests/integration/test_harpocrate_vaults_service_test_connection.py tests/integration/test_harpocrate_vaults_service_m5d.py
uv run ruff format src/rag/services/harpocrate_vaults.py tests/integration/test_harpocrate_vaults_service_test_connection.py tests/integration/test_harpocrate_vaults_service_m5d.py
```

- [ ] **Step 7: Commit**

```powershell
cd ..
git add backend/src/rag/services/harpocrate_vaults.py backend/tests/integration/test_harpocrate_vaults_service_test_connection.py backend/tests/integration/test_harpocrate_vaults_service_m5d.py
git commit -m "feat(M5d): get_wallet_info + test_connection refactoré sur whoami()"
```

---

## Task 4: Service — `list_types` + `list_wallet_secrets`

**Files:**
- Modify: `backend/src/rag/services/harpocrate_vaults.py`
- Modify: `backend/tests/integration/test_harpocrate_vaults_service_m5d.py`

- [ ] **Step 1: Étendre les tests**

Ajouter en bas de `test_harpocrate_vaults_service_m5d.py` :

```python
@pytest.mark.asyncio
async def test_list_types_relays_sdk(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        t_uuid = uuid4()
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.list_types.return_value = [
                MagicMock(
                    type_uuid=t_uuid,
                    type="openai_api_key",
                    sous_type=None,
                    label="OpenAI API key",
                    deprecated=False,
                ),
            ]
            mock_client.return_value = instance
            result = await svc.list_types(conn, seeded.id)
    assert len(result) == 1
    assert result[0].type == "openai_api_key"
    assert result[0].type_uuid == t_uuid


@pytest.mark.asyncio
async def test_list_types_with_q_filter(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.list_types.return_value = []
            mock_client.return_value = instance
            await svc.list_types(conn, seeded.id, q="openai", include_deprecated=True)
            instance.list_types.assert_called_once_with(
                q="openai", include_deprecated=True,
            )


@pytest.mark.asyncio
async def test_list_types_raises_when_vault_absent(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        await conn.execute("DELETE FROM harpocrate_vaults")
        with pytest.raises(VaultNotFoundError):
            await svc.list_types(conn, uuid4())


@pytest.mark.asyncio
async def test_list_wallet_secrets_returns_paginated(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        s_id = uuid4()
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.list_secrets.return_value = MagicMock(
                secrets=[
                    MagicMock(
                        id=s_id,
                        name="anthropic_key",
                        description=None,
                        is_placeholder=False,
                        tags=["env:prod"],
                    ),
                ],
                next_cursor="cursor-1",
            )
            mock_client.return_value = instance
            result = await svc.list_wallet_secrets(conn, seeded.id)
    assert len(result.secrets) == 1
    assert result.secrets[0].id == s_id
    assert result.secrets[0].name == "anthropic_key"
    assert result.next_cursor == "cursor-1"


@pytest.mark.asyncio
async def test_list_wallet_secrets_with_path_filter(
    session_pool: asyncpg.Pool, monkeypatch,
):
    _set_env(monkeypatch)
    await run_migrations(session_pool, MIGRATIONS_DIR)
    svc = HarpocrateVaultsService(Settings())
    async with session_pool.acquire() as conn:
        seeded = await _seed(svc, conn)
        with patch(
            "rag.services.harpocrate_vaults.HarpocrateVaultClient"
        ) as mock_client:
            instance = MagicMock()
            instance.list_secrets.return_value = MagicMock(
                secrets=[], next_cursor=None,
            )
            mock_client.return_value = instance
            await svc.list_wallet_secrets(
                conn, seeded.id,
                path="/api-keys/",
                name_contains="anthropic",
                tag="env:prod",
                limit=100,
            )
            instance.list_secrets.assert_called_once_with(
                tag="env:prod",
                name_contains="anthropic",
                path="/api-keys/",
                limit=100,
            )
```

- [ ] **Step 2: Implémenter dans `harpocrate_vaults.py`**

Ajouter à la classe `HarpocrateVaultsService` :

```python
async def list_types(
    self,
    conn: Connection,
    vault_id: UUID,
    *,
    q: str | None = None,
    include_deprecated: bool = False,
) -> list[SecretTypeSummary]:
    """Relais sur client.types.list() avec mapping en SecretTypeSummary."""
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
            type_uuid=getattr(t, "type_uuid", None) or getattr(t, "id"),
            type=getattr(t, "type"),
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
    """Relais sur client.secrets.list_secrets() avec mapping."""
    vault = await self.get_by_id(conn, vault_id)
    if vault is None:
        raise VaultNotFoundError(str(vault_id))
    api_key = await self.reveal_api_key(conn, vault_id)
    if api_key is None:
        raise VaultNotFoundError(str(vault_id))

    client = HarpocrateVaultClient(url=vault.base_url, token=api_key)
    sdk_resp = client.list_secrets(
        tag=tag, name_contains=name_contains, path=path, limit=limit,
    )
    items = [
        SecretListItem(
            id=getattr(s, "id"),
            name=getattr(s, "name"),
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
```

- [ ] **Step 3: Smoke + collect**

```powershell
cd backend
uv run python -c "from rag.services.harpocrate_vaults import HarpocrateVaultsService; assert hasattr(HarpocrateVaultsService, 'list_types'); assert hasattr(HarpocrateVaultsService, 'list_wallet_secrets'); print('OK')"
uv run pytest tests/integration/test_harpocrate_vaults_service_m5d.py --collect-only -q
```

Expected : `OK`, ~7 tests collectés.

- [ ] **Step 4: Non-régression unit**

```powershell
uv run pytest tests/unit/ -q
```

Expected : 316+ passed.

- [ ] **Step 5: Ruff**

```powershell
uv run ruff check src/rag/services/harpocrate_vaults.py tests/integration/test_harpocrate_vaults_service_m5d.py
uv run ruff format src/rag/services/harpocrate_vaults.py tests/integration/test_harpocrate_vaults_service_m5d.py
```

- [ ] **Step 6: Commit**

```powershell
cd ..
git add backend/src/rag/services/harpocrate_vaults.py backend/tests/integration/test_harpocrate_vaults_service_m5d.py
git commit -m "feat(M5d): service list_types + list_wallet_secrets (relais SDK)"
```

---

## Task 5: Router — 3 nouveaux endpoints HTTP

**Files:**
- Modify: `backend/src/rag/api/admin_harpocrate_vaults.py`
- Create: `backend/tests/api/test_admin_harpocrate_vaults_m5d.py`

- [ ] **Step 1: Écrire les tests HTTP**

Créer `backend/tests/api/test_admin_harpocrate_vaults_m5d.py` :

```python
from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch
from uuid import uuid4

from fastapi.testclient import TestClient


def _payload(**overrides: Any) -> dict[str, Any]:
    p: dict[str, Any] = {
        "name": "rag",
        "label": "Coffre RAG",
        "base_url": "https://harpocrate.yoops.org",
        "api_key_id": "k-001",
        "api_key": "supersecretvalue123",
        "is_default": True,
    }
    p.update(overrides)
    return p


def _create_vault(admin_client: TestClient, admin_headers: dict[str, str]) -> dict:
    r = admin_client.post(
        "/api/admin/harpocrate-vaults", json=_payload(), headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_get_info_endpoint_returns_wallet_info(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    wallet_id = uuid4()
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        instance.whoami.return_value = MagicMock(
            api_key_id="k-001", permissions=["read"], expires_at=None,
        )
        instance.info.return_value = MagicMock(
            wallet_id=wallet_id, name="prod-wallet",
        )
        mc.return_value = instance
        r = admin_client.get(
            f"/api/admin/harpocrate-vaults/{vault['id']}/info",
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["api_key_id"] == "k-001"
    assert body["wallet_name"] == "prod-wallet"


def test_get_info_returns_404_when_vault_absent(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    r = admin_client.get(
        "/api/admin/harpocrate-vaults/00000000-0000-0000-0000-000000000000/info",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_get_types_endpoint_returns_catalog(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    t_uuid = uuid4()
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        instance.list_types.return_value = [
            MagicMock(
                type_uuid=t_uuid,
                type="openai_api_key",
                sous_type=None,
                label="OpenAI",
                deprecated=False,
            ),
        ]
        mc.return_value = instance
        r = admin_client.get(
            f"/api/admin/harpocrate-vaults/{vault['id']}/types",
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body, list)
    assert len(body) == 1
    assert body[0]["type"] == "openai_api_key"


def test_get_secrets_endpoint_returns_list(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    s_id = uuid4()
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        instance.list_secrets.return_value = MagicMock(
            secrets=[
                MagicMock(
                    id=s_id, name="anthropic_key",
                    description=None, is_placeholder=False, tags=[],
                ),
            ],
            next_cursor=None,
        )
        mc.return_value = instance
        r = admin_client.get(
            f"/api/admin/harpocrate-vaults/{vault['id']}/secrets",
            headers=admin_headers,
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["secrets"]) == 1
    assert body["secrets"][0]["name"] == "anthropic_key"
    assert body["next_cursor"] is None


def test_get_secrets_endpoint_respects_query_params(
    admin_client: TestClient, admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        instance.list_secrets.return_value = MagicMock(secrets=[], next_cursor=None)
        mc.return_value = instance
        r = admin_client.get(
            f"/api/admin/harpocrate-vaults/{vault['id']}/secrets",
            params={"path": "/api-keys/", "name_contains": "ant", "limit": 25},
            headers=admin_headers,
        )
    assert r.status_code == 200
    instance.list_secrets.assert_called_once()
    call_kwargs = instance.list_secrets.call_args.kwargs
    assert call_kwargs["path"] == "/api-keys/"
    assert call_kwargs["name_contains"] == "ant"
    assert call_kwargs["limit"] == 25


def test_anonymous_returns_401_on_info(admin_client: TestClient) -> None:
    r = admin_client.get(
        "/api/admin/harpocrate-vaults/00000000-0000-0000-0000-000000000000/info",
    )
    assert r.status_code == 401
```

- [ ] **Step 2: Ajouter les 3 endpoints au router**

Dans `backend/src/rag/api/admin_harpocrate_vaults.py`, ajouter en haut :

```python
from rag.schemas.harpocrate_vaults import (
    SecretListResponse,
    SecretTypeSummary,
    VaultCreateRequest,
    VaultRevealApiKeyResponse,
    VaultRotateApiKeyRequest,
    VaultSummary,
    VaultTestConnectionResult,
    VaultUpdateRequest,
    WalletInfoResponse,
)
```

Ajouter à la fin du fichier (après `reveal_api_key`) :

```python
@router.get("/{vault_id}/info", response_model=WalletInfoResponse)
async def get_vault_info(
    vault_id: UUID, request: Request,
) -> WalletInfoResponse:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            result = await svc.get_wallet_info(conn, vault_id)
        except VaultNotFoundError as exc:
            raise HTTPException(404, "vault not found") from exc
    log.info("vault.info.http", vault_id=str(vault_id), actor=_actor(request))
    return result


@router.get("/{vault_id}/types", response_model=list[SecretTypeSummary])
async def list_vault_types(
    vault_id: UUID,
    request: Request,
    q: str | None = None,
    include_deprecated: bool = False,
) -> list[SecretTypeSummary]:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            return await svc.list_types(
                conn, vault_id, q=q, include_deprecated=include_deprecated,
            )
        except VaultNotFoundError as exc:
            raise HTTPException(404, "vault not found") from exc


@router.get("/{vault_id}/secrets", response_model=SecretListResponse)
async def list_vault_secrets(
    vault_id: UUID,
    request: Request,
    path: str | None = None,
    name_contains: str | None = None,
    tag: str | None = None,
    limit: int = 50,
) -> SecretListResponse:
    svc = request.app.state.harpocrate_vaults_service
    pool = request.app.state.pools.config_pool
    async with pool.acquire() as conn:
        try:
            return await svc.list_wallet_secrets(
                conn, vault_id,
                path=path, name_contains=name_contains, tag=tag, limit=limit,
            )
        except VaultNotFoundError as exc:
            raise HTTPException(404, "vault not found") from exc
```

- [ ] **Step 3: Lancer tests d'intégration HTTP**

```powershell
cd backend
uv run pytest tests/api/test_admin_harpocrate_vaults_m5d.py -v
```

Expected en local : tests SKIPPED faute de TEST_POSTGRES_PASSWORD. Validation prévue contre LXC test côté contrôleur après commit.

- [ ] **Step 4: Smoke import**

```powershell
uv run python -c "from rag.api.admin_harpocrate_vaults import router; routes = [r.path for r in router.routes]; assert any('/info' in p for p in routes); assert any('/types' in p for p in routes); assert any('/secrets' in p for p in routes); print('OK')"
```

Expected : `OK`.

- [ ] **Step 5: Non-régression unit**

```powershell
uv run pytest tests/unit/ -q
```

Expected : 316+ passed.

- [ ] **Step 6: Ruff**

```powershell
uv run ruff check src/rag/api/admin_harpocrate_vaults.py tests/api/test_admin_harpocrate_vaults_m5d.py
uv run ruff format src/rag/api/admin_harpocrate_vaults.py tests/api/test_admin_harpocrate_vaults_m5d.py
```

- [ ] **Step 7: Commit**

```powershell
cd ..
git add backend/src/rag/api/admin_harpocrate_vaults.py backend/tests/api/test_admin_harpocrate_vaults_m5d.py
git commit -m "feat(M5d): router +GET /info /types /secrets (3 endpoints)"
```

---

## Task 6: Deploy LXC 303 + tag

**Files:** _(aucun fichier source modifié — orchestration only)_

- [ ] **Step 1: Push origin dev**

```powershell
git push origin dev
```

- [ ] **Step 2: Deploy LXC 303**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Expected : `Smoke /health … → ok`, version reporte le SHA M5d.

- [ ] **Step 3: Smoke curl**

```powershell
$key = ssh pve "pct exec 303 -- bash -c 'grep RAG_MASTER_KEY /opt/rag/.env | head -1 | cut -d= -f2'"
$key = $key.Trim()
$h = @{ Authorization = "Bearer $key" }

# /info sans coffre → 404 (DB vide sur LXC 303)
Invoke-WebRequest -Uri http://192.168.10.184/api/admin/harpocrate-vaults `
  -Headers $h -UseBasicParsing | Select-Object StatusCode, Content
```

Expected : 200 avec `[]` (la table est vide tant qu'aucun coffre n'est créé via API et que `HARPOCRATE_API_TOKEN_RAG` n'est pas posé en `.env`).

Test optionnel — si l'admin a posé `HARPOCRATE_DEK` + créé un coffre via curl :

```powershell
# Récupérer un vault_id existant
$vaults = Invoke-RestMethod -Uri http://192.168.10.184/api/admin/harpocrate-vaults -Headers $h
if ($vaults.Count -gt 0) {
    $vid = $vaults[0].id
    Invoke-RestMethod -Uri "http://192.168.10.184/api/admin/harpocrate-vaults/$vid/info" -Headers $h
}
```

- [ ] **Step 4: Tag**

```powershell
git tag m5d-backend-done
git push origin m5d-backend-done
```

---

## Self-Review

### Couverture spec → tâches

| Section spec | Tâche(s) |
|---|---|
| §4 Refactor test_connection | Task 3 |
| §5 Schemas Pydantic | Task 2 |
| §6 Wrapper SDK étendu | Task 1 |
| §7 Service nouvelles méthodes | Tasks 3, 4 |
| §8 Router 3 endpoints | Task 5 |
| §9 Tests | Couverts dans chaque task |
| §11 Critères complétion | Couverts par Task 6 |
| §12 Pièges (getattr défensif, mocks) | Inline dans 3, 4, 5 |

### Placeholder scan

Aucun "TBD", "TODO" ou "implement later". Chaque step contient le code à appliquer ou la commande exacte.

### Cohérence types/noms

- `HarpocrateVaultClient` méthodes : `whoami`, `info`, `list_types`, `list_secrets` (Task 1) cohérents avec leur usage dans Tasks 3-4.
- `get_wallet_info`, `list_types`, `list_wallet_secrets` : signatures kwarg-only cohérentes entre Tasks 3-4 et leur consommation dans Task 5 (router).
- Sentinelle `probe_path_used="whoami"` : utilisée Task 3 (service), aucun usage code qui la teste — uniquement informatif côté client.

### Bite-sized check

6 tâches, chacune < 7 steps. Plus court que M5c. Pas de tâche structurante de type "refactor 7 sites" — scope additif uniquement.

---

## Execution Handoff

Plan complet et sauvé. Conformément à la règle `subagent-driven-default`, l'exécution se fait en subagent-driven (fresh subagent par tâche). Le contrôleur :
1. Dispatche T1 (wrapper SDK) — pas de DB, validation par smoke + unit.
2. Dispatche T2 (schemas) — pas de DB, validation par unit.
3. Dispatche T3 (service get_wallet_info + refactor test_connection) — validation LXC test après commit.
4. Dispatche T4 (service list_types + list_secrets) — validation LXC test après commit.
5. Dispatche T5 (router 3 endpoints) — validation LXC test après commit.
6. T6 (deploy + tag) — exécuté par le contrôleur lui-même (pas un subagent).
