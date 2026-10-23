"""Routes « Reconnecter » sur l'app réelle (ticket c3cf13e2).

Session d'admin réelle (compte local), Harpocrate et la sonde du wallet actuel
simulés, test de connexion neutralisé (pas de réseau).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from rag.schemas.harpocrate_vaults import VaultTestConnectionResult
from rag.services.harpocrate_connect import HarpocrateConnectService
from tests.api._helpers import make_app_client
from tests.integration.test_harpocrate_connect_service import API_KEY_ID, FakeHarpocrate
from tests.integration.test_harpocrate_reconnect_service import (
    OTHER_WALLET,
    WALLET,
    FakeWalletProbe,
)

_MASTER = {"Authorization": "Bearer mk_test_e2e_padding_padding_padding_padding"}
_VAULTS = "/api/admin/harpocrate-vaults"
_CONNECT = f"{_VAULTS}/connect"
_CALLBACK = f"{_CONNECT}/callback"
_PASSWORD = "pw-for-tests-123"
_VAULT = {
    "name": "rag-existant",
    "label": "Coffre existant",
    "base_url": "https://vault.example",
    "api_key_id": "k-ancienne",
    "api_key": "hrpv_1_ancienne-cle-du-coffre",
}


@dataclass
class Rig:
    client: TestClient
    harpocrate: FakeHarpocrate
    vault_id: str


@pytest.fixture
def rig(pg_container: str) -> Iterator[Rig]:
    with make_app_client(pg_container) as client:
        client.post(
            "/api/setup/init-admin",
            json={"username": "admin", "email": "admin@example.com", "password": _PASSWORD},
        )
        login = client.post("/auth/local/login", json={"username": "admin", "password": _PASSWORD})
        assert login.status_code == 200
        state = client.app.state  # type: ignore[attr-defined]
        fake = FakeHarpocrate(wallet_id=WALLET)
        state.harpocrate_connect_service = HarpocrateConnectService(
            state.settings,
            state.harpocrate_vaults_service,
            sdk_start=fake.start,
            sdk_finish=fake.finish,
            wallet_probe=FakeWalletProbe(),
        )

        async def _tested(_conn, _vault_id):  # type: ignore[no-untyped-def]
            return VaultTestConnectionResult(ok=True, detail="stub", probe_path_used="stub")

        state.harpocrate_vaults_service.test_connection = _tested
        created = client.post(_VAULTS, json=_VAULT)
        assert created.status_code == 201, created.text
        yield Rig(client, fake, created.json()["id"])


def _redirect_params(response) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    assert response.status_code == 303
    location = urlparse(response.headers["location"])
    assert location.path == "/ui/settings/harpocrate-vaults"
    return parse_qs(location.query)


def _reconnect(rig: Rig) -> dict[str, list[str]]:
    started = rig.client.post(f"{_CONNECT}/reconnect/{rig.vault_id}/start")
    assert started.status_code == 200, started.text
    back = rig.client.get(
        _CALLBACK, params={"code": "c1", "state": rig.harpocrate.state}, follow_redirects=False
    )
    return _redirect_params(back)


def _api_key_id(rig: Rig) -> str:
    return str(rig.client.get(f"{_VAULTS}/{rig.vault_id}").json()["api_key_id"])


def test_reconnect_same_wallet_redirects_with_replaced_key(rig: Rig) -> None:
    params = _reconnect(rig)
    assert params["connect"] == ["reconnected"]
    assert params["vault"] == [rig.vault_id] and params["tested"] == ["true"]
    assert _api_key_id(rig) == str(API_KEY_ID)


def test_reconnect_other_wallet_confirmed_replaces_key_once(rig: Rig) -> None:
    rig.harpocrate.wallet_id = OTHER_WALLET
    params = _reconnect(rig)
    assert params["connect"] == ["confirm_wallet"]
    request_id = params["request"][0]
    assert _api_key_id(rig) == "k-ancienne"

    pending = rig.client.get(f"{_CONNECT}/pending/{request_id}")
    assert pending.status_code == 200
    assert pending.json()["previous_wallet_id"] == str(WALLET)
    assert pending.json()["new_wallet_id"] == str(OTHER_WALLET)

    confirmed = rig.client.post(f"{_CONNECT}/pending/{request_id}/confirm")
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["tested"] is True
    assert _api_key_id(rig) == str(API_KEY_ID)
    # Le jeton de décision a quitté la session : un rejeu ne trouve plus rien.
    again = rig.client.post(f"{_CONNECT}/pending/{request_id}/confirm")
    assert again.status_code == 409


def test_reconnect_other_wallet_cancelled_keeps_old_key(rig: Rig) -> None:
    rig.harpocrate.wallet_id = OTHER_WALLET
    request_id = _reconnect(rig)["request"][0]
    cancelled = rig.client.post(f"{_CONNECT}/pending/{request_id}/cancel")
    assert cancelled.status_code == 204
    assert _api_key_id(rig) == "k-ancienne"
    assert rig.client.get(f"{_CONNECT}/pending/{request_id}").status_code == 404


def test_reconnect_denied_keeps_old_key(rig: Rig) -> None:
    rig.client.post(f"{_CONNECT}/reconnect/{rig.vault_id}/start")
    back = rig.client.get(
        _CALLBACK,
        params={"error": "access_denied", "state": rig.harpocrate.state},
        follow_redirects=False,
    )
    assert _redirect_params(back)["connect_error"] == ["denied"]
    assert _api_key_id(rig) == "k-ancienne"


def test_reconnect_start_refusals(rig: Rig) -> None:
    with_master = rig.client.post(f"{_CONNECT}/reconnect/{rig.vault_id}/start", headers=_MASTER)
    assert with_master.status_code == 400
    assert with_master.json()["detail"] == "connect_requires_browser_session"
    assert rig.client.post(f"{_CONNECT}/reconnect/{uuid4()}/start").status_code == 404
    assert rig.harpocrate.calls == []


def test_reconnect_routes_refuse_anonymous(pg_container: str) -> None:
    some = uuid4()
    with make_app_client(pg_container) as client:
        assert client.post(f"{_CONNECT}/reconnect/{some}/start").status_code == 401
        assert client.get(f"{_CONNECT}/pending/{some}").status_code == 401
        assert client.post(f"{_CONNECT}/pending/{some}/confirm").status_code == 401
        assert client.post(f"{_CONNECT}/pending/{some}/cancel").status_code == 401
