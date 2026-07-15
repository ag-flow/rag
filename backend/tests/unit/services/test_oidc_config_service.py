from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.services.oidc import OidcConfig, OidcService


def _fake_pool_for_get(returning_row: dict | None) -> MagicMock:
    """Mock asyncpg.Pool pour get_config (uniquement fetchrow)."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value=returning_row)
    return pool


def _fake_pool_for_upsert() -> tuple[MagicMock, MagicMock]:
    """Mock pool + conn pour upsert_config (acquire + transaction).

    Returns (pool, conn) so the test can inspect conn.execute calls.
    """
    conn = MagicMock()
    conn.execute = AsyncMock()
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)

    pool = MagicMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    return pool, conn


@pytest.mark.asyncio
async def test_get_config_returns_none_when_empty() -> None:
    pool = _fake_pool_for_get(returning_row=None)
    svc = OidcService(
        config_pool=pool,
        public_url="https://rag.example.com",
    )
    assert await svc.get_config() is None


@pytest.mark.asyncio
async def test_get_config_returns_oidc_config_when_present() -> None:
    pool = _fake_pool_for_get(
        returning_row={
            "issuer": "https://kc.example.com/realms/r",
            "client_id": "rag-service",
        }
    )
    svc = OidcService(
        config_pool=pool,
        public_url="https://rag.example.com",
    )
    cfg = await svc.get_config()
    assert cfg == OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
    )


@pytest.mark.asyncio
async def test_upsert_config_inserts_first_time() -> None:
    """`upsert_config` doit DELETE puis INSERT (1 row max en table)."""
    pool, conn = _fake_pool_for_upsert()
    svc = OidcService(
        config_pool=pool,
        public_url="https://rag.example.com",
    )
    cfg = await svc.upsert_config(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
    )
    assert cfg.client_id == "rag-service"
    assert cfg.issuer == "https://kc.example.com/realms/r"
    # 2 execute : DELETE + INSERT
    assert conn.execute.await_count == 2
    # 1er execute : DELETE
    delete_call = conn.execute.await_args_list[0]
    assert "DELETE FROM oidc_config" in delete_call.args[0]
    # 2e execute : INSERT
    insert_call = conn.execute.await_args_list[1]
    assert "INSERT INTO oidc_config" in insert_call.args[0]
    assert insert_call.args[1] == "https://kc.example.com/realms/r"
    assert insert_call.args[2] == "rag-service"


@pytest.mark.asyncio
async def test_upsert_config_replaces_existing() -> None:
    """Le pattern DELETE+INSERT garantit 1 row max même appelé 2 fois."""
    pool, conn = _fake_pool_for_upsert()
    svc = OidcService(
        config_pool=pool,
        public_url="https://rag.example.com",
    )
    await svc.upsert_config(
        issuer="https://kc-old/realms/r",
        client_id="old",
    )
    conn.execute.reset_mock()
    await svc.upsert_config(
        issuer="https://kc-new/realms/r",
        client_id="new",
    )
    # Toujours DELETE + INSERT
    assert conn.execute.await_count == 2
