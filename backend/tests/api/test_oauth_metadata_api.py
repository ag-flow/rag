"""Métadonnées RFC 9728 et 401 de `/mcp` sur l'app réelle (ticket 3d457a26)."""

from __future__ import annotations

from tests.api._helpers import make_app_client

_ISSUER = "https://idp.example/realms/yoops"
_METADATA = "/.well-known/oauth-protected-resource/mcp"


def test_metadata_announces_idp_once_oidc_configured(pg_container: str) -> None:
    with make_app_client(pg_container) as client:
        pool = client.app.state.pools.config_pool  # type: ignore[attr-defined]
        assert client.get(_METADATA).status_code == 404  # aucun IdP : rien à annoncer
        client.portal.call(pool.execute, "DELETE FROM oidc_config")
        client.portal.call(
            pool.execute,
            "INSERT INTO oidc_config (issuer, client_id) VALUES ($1, 'ragflow-ui')",
            _ISSUER,
        )
        for path in (_METADATA, "/.well-known/oauth-protected-resource"):
            resp = client.get(path)
            assert resp.status_code == 200, resp.text
            assert resp.json()["resource"] == "http://testserver/mcp"
            assert resp.json()["authorization_servers"] == [_ISSUER]
        client.portal.call(pool.execute, "DELETE FROM oidc_config")


def test_mcp_without_token_designates_metadata(pg_container: str) -> None:
    with make_app_client(pg_container) as client:
        resp = client.post("/mcp", json={})
    assert resp.status_code == 401
    assert resp.headers["www-authenticate"] == (
        f'Bearer resource_metadata="http://testserver{_METADATA}"'
    )
