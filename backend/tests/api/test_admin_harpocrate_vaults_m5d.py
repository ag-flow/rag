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


def _create_vault(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> dict[str, Any]:
    r = admin_client.post(
        "/api/admin/harpocrate-vaults",
        json=_payload(),
        headers=admin_headers,
    )
    assert r.status_code == 201, r.text
    return r.json()


def test_get_info_endpoint_returns_wallet_info(
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    wallet_id = uuid4()
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        instance.whoami.return_value = MagicMock(
            api_key_id="k-001",
            permissions=["read"],
            expires_at=None,
        )
        # MagicMock(name=...) consume _mock_name interne → set après instanciation
        wallet_mock = MagicMock(wallet_id=wallet_id)
        wallet_mock.name = "prod-wallet"
        instance.info.return_value = wallet_mock
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
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    r = admin_client.get(
        "/api/admin/harpocrate-vaults/00000000-0000-0000-0000-000000000000/info",
        headers=admin_headers,
    )
    assert r.status_code == 404


def test_get_types_endpoint_returns_catalog(
    admin_client: TestClient,
    admin_headers: dict[str, str],
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
    admin_client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    vault = _create_vault(admin_client, admin_headers)
    s_id = uuid4()
    with patch("rag.services.harpocrate_vaults.HarpocrateVaultClient") as mc:
        instance = MagicMock()
        secret_mock = MagicMock(
            id=s_id,
            description=None,
            is_placeholder=False,
            tags=[],
        )
        secret_mock.name = "anthropic_key"
        instance.list_secrets.return_value = MagicMock(
            secrets=[secret_mock],
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
    admin_client: TestClient,
    admin_headers: dict[str, str],
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
