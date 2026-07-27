"""Contrôle d'accès aux coffres Harpocrate (`_check_vault_access`).

Option A : le coffre par défaut (`is_default`) est partagé — lisible ET
modifiable par tout admin authentifié, quel que soit son `owner_id`. Les
coffres non-default restent réservés à leur propriétaire, en lecture comme
en écriture.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from rag.api.admin_harpocrate_vaults import router
from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.auth.owner import email_to_owner_id
from rag.schemas.harpocrate_vaults import VaultSummary

OWNER_A = email_to_owner_id("alice@example.com")
OWNER_B = email_to_owner_id("bob@example.com")


class _AcquireCM:
    """Context manager asynchrone minimal pour `pool.acquire()`."""

    def __init__(self, conn: object) -> None:
        self._conn = conn

    async def __aenter__(self) -> object:
        return self._conn

    async def __aexit__(self, *_exc: object) -> bool:
        return False


def _vault(*, is_default: bool, owner_id: str, api_key_id: str = "k-001") -> VaultSummary:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    return VaultSummary(
        id=uuid4(),
        name="default" if is_default else "private",
        label="lbl",
        base_url="https://harpocrate.yoops.org",
        api_key_id=api_key_id,
        probe_path=None,
        is_default=is_default,
        owner_id=owner_id,
        created_at=now,
        updated_at=now,
    )


def _client(vault: VaultSummary, requester_owner: str, monkeypatch) -> TestClient:
    rotated = _vault(is_default=vault.is_default, owner_id=vault.owner_id, api_key_id="k-002")
    svc = MagicMock()
    svc.get_by_id = AsyncMock(return_value=vault)
    svc.rotate_api_key = AsyncMock(return_value=rotated)

    pool = MagicMock()
    pool.acquire = MagicMock(return_value=_AcquireCM(MagicMock()))

    app = FastAPI()
    app.state.harpocrate_vaults_service = svc
    app.state.pools = MagicMock()
    app.state.pools.config_pool = pool
    app.include_router(router)
    app.dependency_overrides[require_master_key_or_authenticated_admin] = lambda: None
    monkeypatch.setattr(
        "rag.api.admin_harpocrate_vaults.get_current_owner_id",
        lambda _request: requester_owner,
    )
    return TestClient(app)


def _rotate(client: TestClient, vault_id: object):
    return client.post(
        f"/api/admin/harpocrate-vaults/{vault_id}/rotate-api-key",
        json={"api_key_id": "k-002", "api_key": "newsecretvalue123"},
    )


class TestRotateApiKeyAccess:
    def test_non_owner_can_rotate_default_vault(self, monkeypatch) -> None:
        """Un admin non-propriétaire peut rotationner la clé du coffre partagé."""
        vault = _vault(is_default=True, owner_id=OWNER_A)
        client = _client(vault, requester_owner=OWNER_B, monkeypatch=monkeypatch)

        resp = _rotate(client, vault.id)

        assert resp.status_code == 200
        assert resp.json()["api_key_id"] == "k-002"

    def test_owner_can_rotate_own_private_vault(self, monkeypatch) -> None:
        vault = _vault(is_default=False, owner_id=OWNER_A)
        client = _client(vault, requester_owner=OWNER_A, monkeypatch=monkeypatch)

        assert _rotate(client, vault.id).status_code == 200

    def test_non_owner_cannot_rotate_private_vault(self, monkeypatch) -> None:
        """Un coffre non-default reste protégé : 403 pour un non-propriétaire."""
        vault = _vault(is_default=False, owner_id=OWNER_A)
        client = _client(vault, requester_owner=OWNER_B, monkeypatch=monkeypatch)

        assert _rotate(client, vault.id).status_code == 403
