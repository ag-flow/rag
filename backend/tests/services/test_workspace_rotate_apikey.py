from __future__ import annotations

from contextlib import asynccontextmanager
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.auth.workspace_auth import ApiKeyCache
from rag.services.workspaces import rotate_apikey


def _make_pool(api_key_ref: str) -> MagicMock:
    """Fabrique un pool asyncpg mocké avec fetchrow, execute et acquire."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={"api_key_ref": api_key_ref})
    pool.execute = AsyncMock(return_value="UPDATE 1")

    # acquire() est utilisé comme async context manager pour passer conn à write_secret
    fake_conn = MagicMock()

    @asynccontextmanager
    async def _acquire():
        yield fake_conn

    pool.acquire = _acquire
    return pool


@pytest.fixture
def existing_api_key_ref() -> str:
    return "${vault://rag:wsapi_test1}"


@pytest.fixture
def cache_with_old_entry(existing_api_key_ref: str) -> ApiKeyCache:
    cache = ApiKeyCache()
    cache.put(existing_api_key_ref, "old-clear-value")
    return cache


@pytest.mark.asyncio
async def test_rotate_apikey_updates_harpocrate_value_and_fingerprint(
    existing_api_key_ref: str,
    cache_with_old_entry: ApiKeyCache,
) -> None:
    """rotate_apikey : génère nouvelle clé, l'écrit dans Harpocrate sous le
    même path, met à jour le fingerprint en DB."""
    pool = _make_pool(existing_api_key_ref)

    harpo = MagicMock()
    harpo.write_secret = AsyncMock()

    await rotate_apikey(
        name="test1",
        config_pool=pool,
        harpocrate_vaults_service=harpo,
        apikey_cache=cache_with_old_entry,
    )

    # write_secret appelé avec vault="rag", path="wsapi_test1", value=<new_key>
    harpo.write_secret.assert_awaited_once()
    call_args = harpo.write_secret.call_args
    assert call_args.kwargs["vault_name"] == "rag"
    assert call_args.kwargs["path"] == "wsapi_test1"
    new_api_key = call_args.kwargs["value"]
    assert isinstance(new_api_key, str) and len(new_api_key) > 0

    # UPDATE workspaces SET api_key_fingerprint = ? WHERE name = ?
    pool.execute.assert_awaited_once()
    update_args = pool.execute.call_args.args
    assert "api_key_fingerprint" in update_args[0]
    new_fp = update_args[1]
    assert new_fp == sha256(new_api_key.encode()).hexdigest()


@pytest.mark.asyncio
async def test_rotate_apikey_invalidates_cache(
    existing_api_key_ref: str,
    cache_with_old_entry: ApiKeyCache,
) -> None:
    """L'ancien clair est évincé du cache après rotation."""
    pool = _make_pool(existing_api_key_ref)
    harpo = MagicMock()
    harpo.write_secret = AsyncMock()

    await rotate_apikey(
        name="test1",
        config_pool=pool,
        harpocrate_vaults_service=harpo,
        apikey_cache=cache_with_old_entry,
    )

    # Cache invalidé
    assert cache_with_old_entry.get(existing_api_key_ref) is None


@pytest.mark.asyncio
async def test_rotate_apikey_returns_new_clear_value(existing_api_key_ref: str) -> None:
    """Le retour contient bien la nouvelle api_key en clair."""
    pool = _make_pool(existing_api_key_ref)
    harpo = MagicMock()
    harpo.write_secret = AsyncMock()

    result = await rotate_apikey(
        name="test1",
        config_pool=pool,
        harpocrate_vaults_service=harpo,
        apikey_cache=ApiKeyCache(),
    )

    new_api_key = harpo.write_secret.call_args.kwargs["value"]
    assert result == {"api_key": new_api_key}


@pytest.mark.asyncio
async def test_rotate_apikey_harpocrate_write_failed_no_db_update(
    existing_api_key_ref: str,
) -> None:
    """Si write_secret échoue, pas d'UPDATE en DB, exception propagée."""
    from rag.api.errors import HarpocrateWriteFailed

    pool = _make_pool(existing_api_key_ref)
    harpo = MagicMock()
    harpo.write_secret = AsyncMock(side_effect=HarpocrateWriteFailed("test failure"))

    with pytest.raises(HarpocrateWriteFailed):
        await rotate_apikey(
            name="test1",
            config_pool=pool,
            harpocrate_vaults_service=harpo,
            apikey_cache=ApiKeyCache(),
        )

    pool.execute.assert_not_awaited()
