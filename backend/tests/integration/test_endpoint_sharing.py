"""Visibilité et partage des endpoints (migration 095, epic f3cc98a8).

La règle « utilisable = coffre visible OU partagé à tous OU partagé à moi » est
la seule barrière entre un tiers et les clés du coffre d'autrui : chaque refus
est un test.
"""

from __future__ import annotations

from uuid import UUID

import asyncpg
import pytest

from rag.auth.owner import principal_to_owner_id
from rag.schemas.endpoint_sharing import EndpointSharingUpdate
from rag.services import endpoint_sharing as svc
from rag.services.vault_endpoints import get_endpoint

_ALICE = "alice@example.com"  # propriétaire du coffre privé
_BOB = "bob@example.com"
_CAROL = "carol@example.com"
_ALICE_ID = principal_to_owner_id(_ALICE)
_BOB_ID = principal_to_owner_id(_BOB)
_CAROL_ID = principal_to_owner_id(_CAROL)


async def _vault(conn: asyncpg.Connection, name: str, *, owner: str, default: bool) -> UUID:
    vault_id: UUID = await conn.fetchval(
        "INSERT INTO harpocrate_vaults "
        "(id, name, label, base_url, api_key_id, api_key_encrypted, is_default, owner_id) "
        "VALUES (gen_random_uuid(), $1, $1, 'https://harpo', 'k', "
        "pgp_sym_encrypt('s', 'passphrase-of-at-least-32-characters-long'), $2, $3) "
        "RETURNING id",
        name,
        default,
        owner,
    )
    return vault_id


async def _endpoint(conn: asyncpg.Connection, vault_id: UUID, slug: str) -> UUID:
    endpoint_id: UUID = await conn.fetchval(
        "INSERT INTO vault_endpoints (vault_id, label, slug, indexer_provider, indexer_model, "
        "indexer_api_key_ref) VALUES ($1, $2, $2, 'openai', 'text-embedding-3-small', "
        "'${vault://private:openai}') RETURNING id",
        vault_id,
        slug,
    )
    return endpoint_id


async def _user(conn: asyncpg.Connection, email: str) -> UUID:
    user_id: UUID = await conn.fetchval(
        "INSERT INTO users (username, email, password_hash) VALUES ($1, $1, '') RETURNING id",
        email,
    )
    return user_id


@pytest.fixture
async def world(migrated: asyncpg.Pool) -> dict[str, UUID]:
    async with migrated.acquire() as conn:
        private = await _vault(conn, "private", owner=_ALICE_ID, default=False)
        shared_default = await _vault(conn, "rag", owner="", default=True)
        return {
            "private_ep": await _endpoint(conn, private, "alice-ep"),
            "default_ep": await _endpoint(conn, shared_default, "default-ep"),
            "bob": await _user(conn, _BOB),
            "carol": await _user(conn, _CAROL),
            "alice": await _user(conn, _ALICE),
        }


async def _usable_ids(conn: asyncpg.Connection, owner_id: str) -> set[UUID]:
    return {ep.id for ep in await svc.db_list_usable_endpoints(conn, owner_id=owner_id)}


@pytest.mark.asyncio
async def test_unshared_private_endpoint_is_invisible_to_third_party(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        assert await _usable_ids(conn, _BOB_ID) == {world["default_ep"]}
        assert (
            await svc.db_get_usable_endpoint(
                conn, owner_id=_BOB_ID, endpoint_id=world["private_ep"]
            )
            is None
        )
        assert (
            await svc.db_find_usable_endpoint_by_slug(
                conn, owner_id=_BOB_ID, vault="private", endpoint="alice-ep"
            )
            is None
        )


@pytest.mark.asyncio
async def test_owner_sees_own_endpoint_as_owned(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        ep = await svc.db_get_usable_endpoint(
            conn, owner_id=_ALICE_ID, endpoint_id=world["private_ep"]
        )
    assert ep is not None
    assert ep.access == "owned"


@pytest.mark.asyncio
async def test_shared_with_all_makes_endpoint_usable_by_anyone(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        await svc.db_set_sharing(
            conn,
            endpoint_id=world["private_ep"],
            req=EndpointSharingUpdate(shared_with_all=True),
        )
        found = await svc.db_find_usable_endpoint_by_slug(
            conn, owner_id=_CAROL_ID, vault="private", endpoint="alice-ep"
        )
    assert found is not None
    assert found.access == "shared"


@pytest.mark.asyncio
async def test_named_share_grants_only_the_named_user(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        await svc.db_set_sharing(
            conn,
            endpoint_id=world["private_ep"],
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["bob"]]),
        )
        assert world["private_ep"] in await _usable_ids(conn, _BOB_ID)
        assert world["private_ep"] not in await _usable_ids(conn, _CAROL_ID)


@pytest.mark.asyncio
async def test_named_share_matches_email_case_insensitively(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    """owner_id = sha256(lower(email)) : le prédicat SQL doit dériver pareil."""
    async with migrated.acquire() as conn:
        await conn.execute("UPDATE users SET email = 'Bob@Example.com' WHERE id = $1", world["bob"])
        await svc.db_set_sharing(
            conn,
            endpoint_id=world["private_ep"],
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["bob"]]),
        )
        assert world["private_ep"] in await _usable_ids(conn, _BOB_ID)


@pytest.mark.asyncio
async def test_named_share_matches_non_ascii_email_like_python_owner_id(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    """Le lower() de Postgres ne replie pas « É » comme Python : l'owner_id du
    bénéficiaire doit venir de `principal_to_owner_id`, pas d'un calcul SQL."""
    async with migrated.acquire() as conn:
        elodie = await _user(conn, "Élodie@example.com")
        await svc.db_set_sharing(
            conn,
            endpoint_id=world["private_ep"],
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[elodie]),
        )
        owner = principal_to_owner_id("élodie@example.com")
        assert world["private_ep"] in await _usable_ids(conn, owner)


@pytest.mark.asyncio
async def test_set_sharing_replaces_previous_beneficiaries(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        ep = world["private_ep"]
        await svc.db_set_sharing(
            conn,
            endpoint_id=ep,
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["bob"]]),
        )
        out = await svc.db_set_sharing(
            conn,
            endpoint_id=ep,
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["carol"]]),
        )
        assert [u.email for u in out.users] == [_CAROL]
        assert ep not in await _usable_ids(conn, _BOB_ID)
        endpoint = await get_endpoint(conn, endpoint_id=ep)
    assert endpoint is not None
    assert endpoint.shared_user_count == 1
    assert endpoint.shared_with_all is False


@pytest.mark.asyncio
async def test_set_sharing_with_unknown_user_changes_nothing(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    ep = world["private_ep"]
    async with migrated.acquire() as conn:
        await svc.db_set_sharing(
            conn,
            endpoint_id=ep,
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["bob"]]),
        )
        with pytest.raises(svc.UnknownShareUserError):
            await svc.db_set_sharing(
                conn,
                endpoint_id=ep,
                req=EndpointSharingUpdate(
                    shared_with_all=True,
                    user_ids=[UUID("00000000-0000-4000-8000-000000000000")],
                ),
            )
        state = await svc.db_get_sharing(conn, endpoint_id=ep)
    assert state.shared_with_all is False
    assert [u.email for u in state.users] == [_BOB]


@pytest.mark.asyncio
async def test_deleting_user_removes_the_share(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        await svc.db_set_sharing(
            conn,
            endpoint_id=world["private_ep"],
            req=EndpointSharingUpdate(shared_with_all=False, user_ids=[world["bob"]]),
        )
        await conn.execute("DELETE FROM users WHERE id = $1", world["bob"])
        state = await svc.db_get_sharing(conn, endpoint_id=world["private_ep"])
    assert state.users == []


@pytest.mark.asyncio
async def test_get_sharing_of_unknown_endpoint_raises(migrated: asyncpg.Pool) -> None:
    async with migrated.acquire() as conn:
        with pytest.raises(LookupError):
            await svc.db_get_sharing(conn, endpoint_id=UUID("00000000-0000-4000-8000-000000000001"))


@pytest.mark.asyncio
async def test_share_candidates_exclude_the_caller(
    migrated: asyncpg.Pool, world: dict[str, UUID]
) -> None:
    async with migrated.acquire() as conn:
        candidates = await svc.db_list_share_candidates(conn, exclude_owner_id=_ALICE_ID)
    assert {c.email for c in candidates} == {_BOB, _CAROL}
