from __future__ import annotations

import time

import asyncpg
import bcrypt
import pytest

from rag.services.local_auth import LocalAuthService

_PASSWORD = "correctpwd"
_USERNAME = "admin"
_EMAIL = "admin@example.com"


def _hash(password: str = _PASSWORD) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
async def local_auth(session_pool: asyncpg.Pool) -> LocalAuthService:
    return LocalAuthService(pool=session_pool, ttl_seconds=3600)


@pytest.fixture
async def local_auth_with_user(session_pool: asyncpg.Pool) -> LocalAuthService:
    svc = LocalAuthService(pool=session_pool, ttl_seconds=3600)
    await svc.create_user(username=_USERNAME, email=_EMAIL, password_hash=_hash())
    return svc


@pytest.mark.asyncio
async def test_user_count_empty_returns_zero(local_auth: LocalAuthService) -> None:
    assert await local_auth.user_count() == 0


@pytest.mark.asyncio
async def test_user_count_after_create_returns_one(local_auth: LocalAuthService) -> None:
    await local_auth.create_user(username=_USERNAME, email=_EMAIL, password_hash=_hash())
    assert await local_auth.user_count() == 1


@pytest.mark.asyncio
async def test_verify_correct_credentials_returns_email(
    local_auth_with_user: LocalAuthService,
) -> None:
    result = await local_auth_with_user.verify(username=_USERNAME, password=_PASSWORD)
    assert result == _EMAIL


@pytest.mark.asyncio
async def test_verify_wrong_password_returns_none(
    local_auth_with_user: LocalAuthService,
) -> None:
    assert await local_auth_with_user.verify(username=_USERNAME, password="wrong") is None


@pytest.mark.asyncio
async def test_verify_unknown_user_returns_none(
    local_auth_with_user: LocalAuthService,
) -> None:
    assert await local_auth_with_user.verify(username="nobody", password=_PASSWORD) is None


@pytest.mark.asyncio
async def test_verify_no_users_returns_none(local_auth: LocalAuthService) -> None:
    assert await local_auth.verify(username=_USERNAME, password=_PASSWORD) is None


def test_build_session_payload_sets_correct_fields() -> None:
    from unittest.mock import MagicMock
    svc = LocalAuthService(pool=MagicMock(), ttl_seconds=3600)
    before = int(time.time())
    payload = svc.build_session_payload(_USERNAME, _EMAIL)
    after = int(time.time())
    assert payload["username"] == _USERNAME
    assert payload["email"] == _EMAIL
    assert before + 3600 <= payload["expires_at"] <= after + 3600
