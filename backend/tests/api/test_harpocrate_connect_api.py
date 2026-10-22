"""Routes « Connecter à Harpocrate » sur l'app réelle (ticket 8ae1487f).

Session d'admin réelle (compte local), Harpocrate simulé par les doublures du
test de service, test de connexion neutralisé (pas de réseau).
"""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from rag.schemas.harpocrate_vaults import VaultTestConnectionResult
from rag.services.harpocrate_connect import HarpocrateConnectService
from tests.api._helpers import make_app_client
from tests.integration.test_harpocrate_connect_service import FakeHarpocrate

_MASTER = {"Authorization": "Bearer mk_test_e2e_padding_padding_padding_padding"}
_START = "/api/admin/harpocrate-vaults/connect/start"
_CALLBACK = "/api/admin/harpocrate-vaults/connect/callback"
_PASSWORD = "pw-for-tests-123"
_IDENTITY = {"name": "rag-connect", "label": "Coffre connecté", "base_url": "https://vault.example"}


@pytest.fixture
def session_client(pg_container: str) -> Iterator[tuple[TestClient, FakeHarpocrate]]:
    with make_app_client(pg_container) as client:
        client.post(
            "/api/setup/init-admin",
            json={
                "username": "admin",
                "email": "admin@example.com",
                "password": "pw-for-tests-123",
            },
        )
        login = client.post("/auth/local/login", json={"username": "admin", "password": _PASSWORD})
        assert login.status_code == 200
        state = client.app.state  # type: ignore[attr-defined]
        fake = FakeHarpocrate()
        state.harpocrate_connect_service = HarpocrateConnectService(
            state.settings,
            state.harpocrate_vaults_service,
            sdk_start=fake.start,
            sdk_finish=fake.finish,
        )

        async def _tested(_conn, _vault_id):  # type: ignore[no-untyped-def]
            return VaultTestConnectionResult(ok=True, detail="stub", probe_path_used="stub")

        state.harpocrate_vaults_service.test_connection = _tested
        yield client, fake


def _redirect_params(response) -> dict[str, list[str]]:  # type: ignore[no-untyped-def]
    assert response.status_code == 303
    location = urlparse(response.headers["location"])
    assert location.path == "/ui/settings/harpocrate-vaults"
    return parse_qs(location.query)


def test_connect_nominal_redirects_to_ui_with_created_vault(session_client) -> None:
    client, fake = session_client
    started = client.post(_START, json=_IDENTITY)
    assert started.status_code == 200, started.text
    assert started.json()["browser_url"].startswith("https://vault.example/connect?")
    # L'URL de retour envoyée à Harpocrate est dérivée de l'adresse d'appel.
    assert fake.calls[0][1][2] == f"http://testserver{_CALLBACK}"

    back = client.get(_CALLBACK, params={"code": "c1", "state": fake.state}, follow_redirects=False)
    params = _redirect_params(back)
    assert params["connect"] == ["ok"] and params["tested"] == ["true"]
    vaults = client.get("/api/admin/harpocrate-vaults").json()
    assert [v["name"] for v in vaults] == ["rag-connect"]
    # Ni le token ni le code ne repartent vers le navigateur.
    assert "hrpv_1" not in back.headers["location"]


def test_connect_replay_after_success_reports_state_error(session_client) -> None:
    client, fake = session_client
    client.post(_START, json=_IDENTITY)
    client.get(_CALLBACK, params={"code": "c1", "state": fake.state}, follow_redirects=False)
    again = client.get(
        _CALLBACK, params={"code": "c1", "state": fake.state}, follow_redirects=False
    )
    # La liaison a été retirée de la session au premier retour.
    assert _redirect_params(again)["connect_error"] == ["state_unknown"]
    assert len(client.get("/api/admin/harpocrate-vaults").json()) == 1


def test_connect_denied_redirects_with_denied(session_client) -> None:
    client, fake = session_client
    client.post(_START, json=_IDENTITY)
    back = client.get(
        _CALLBACK, params={"error": "access_denied", "state": fake.state}, follow_redirects=False
    )
    assert _redirect_params(back)["connect_error"] == ["denied"]
    assert client.get("/api/admin/harpocrate-vaults").json() == []


def test_connect_start_with_master_key_refused(session_client) -> None:
    client, fake = session_client
    resp = client.post(_START, json=_IDENTITY, headers=_MASTER)
    assert resp.status_code == 400
    assert resp.json()["detail"] == "connect_requires_browser_session"
    assert fake.calls == []


def test_connect_routes_refuse_anonymous(pg_container: str) -> None:
    with make_app_client(pg_container) as client:
        assert client.post(_START, json=_IDENTITY).status_code == 401
        assert client.get(_CALLBACK, params={"code": "c", "state": "s"}).status_code == 401


def test_connect_start_undeclared_client_returns_values_to_declare(session_client) -> None:
    """invalid_client : la réponse dit quel client_id et quelle URL déclarer."""
    from harpocrate.exceptions import ConnectError

    client, fake = session_client
    fake.start_error = ConnectError("invalid_client")
    resp = client.post(_START, json=_IDENTITY)
    assert resp.status_code == 409
    assert resp.json()["detail"] == {
        "reason": "client_not_declared",
        "client_id": "ragflow",
        "redirect_uri": f"http://testserver{_CALLBACK}",
    }
