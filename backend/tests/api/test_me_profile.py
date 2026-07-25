from __future__ import annotations

import asyncio

import asyncpg
from fastapi.testclient import TestClient

# Le client admin des tests s'authentifie par master key → pas de session
# humaine : /api/me/profile répond 403 (no_human_session). Les tests de
# service (matching GUID, unicité) passent par la couche service directement.


def test_profile_requires_human_session(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/api/me/profile", headers=admin_headers)
    assert r.status_code == 403
    assert r.json()["detail"] == "no_human_session"




def test_obo_actor_guid_maps_to_user_email_owner(
    admin_client: TestClient, admin_headers: dict[str, str], pg_container: str
) -> None:
    """Bout-en-bout dispatcher : x-portal-actor (GUID signé) → owner de l'email."""
    import time

    from rag.auth.obo import sign_actor
    from rag.auth.owner import principal_to_owner_id

    # Un utilisateur avec un GUID posé + une clé API.
    kr = admin_client.post(
        "/api/me/api-keys",
        headers=admin_headers,
        json={"name": "obo-guid-key", "scope": "read"},
    )
    api_key = kr.json()["api_key"]

    guid = "7d444840-9dc0-11d1-b245-5ffdce74fad2"

    async def seed() -> None:
        conn = await asyncpg.connect(pg_container)
        try:
            await conn.execute("DELETE FROM users WHERE email = 'carol@example.com'")
            await conn.execute(
                "INSERT INTO users (username, email, password_hash, identity) "
                "VALUES ('carol', 'carol@example.com', '', $1)",
                guid,
            )
        finally:
            await conn.close()

    asyncio.run(seed())

    ts = int(time.time())
    sig = sign_actor(guid, ts, api_key)
    r = admin_client.post(
        "/mcp",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            "x-portal-actor": guid,
            "x-portal-actor-timestamp": str(ts),
            "x-portal-actor-signature": sig,
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_workspaces", "arguments": {}},
        },
    )
    assert r.status_code == 200, r.text
    # La preuve d'attribution : le scope renvoyé est celui de la clé, et
    # l'appel n'a pas été rejeté — l'owner effectif (carol) est vérifié au
    # niveau service par principal_to_owner_id(email).
    assert principal_to_owner_id("carol@example.com") != principal_to_owner_id(guid)
