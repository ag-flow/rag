"""Parcours « Connecter à Harpocrate » côté ragflow (ticket 8ae1487f).

Harpocrate est simulé : `start` / `finish` du SDK sont remplacés par des
doublures qui enregistrent leurs appels. La base est réelle (migrations
appliquées), pour éprouver le chiffrement de l'état, la liaison de session et
la consommation unique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from harpocrate.connect import ConnectState
from harpocrate.exceptions import ConnectError

from rag.config import Settings
from rag.db.migrations import run_migrations
from rag.schemas.harpocrate_vaults import VaultIdentity
from rag.services.harpocrate_connect import (
    CONNECT_PERMISSIONS,
    ConnectFlowError,
    HarpocrateConnectService,
)
from rag.services.harpocrate_vaults import HarpocrateVaultsService

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
OWNER = "a" * 64
OTHER_OWNER = "b" * 64
REDIRECT = "https://rag.example/api/admin/harpocrate-vaults/connect/callback"
API_KEY_ID = UUID("11111111-2222-3333-4444-555555555555")
TOKEN = "hrpv_1_token-complet-obtenu-par-le-parcours"
_INSERT_TAKEN_NAME = (
    "INSERT INTO harpocrate_vaults (id, name, label, base_url, api_key_id, api_key_encrypted) "
    "VALUES (gen_random_uuid(), 'rag-connect', 'x', 'https://v', 'k', 'x'::bytea)"
)


@dataclass
class FakeHarpocrate:
    """Doublure du SDK : un state connu, un résultat ou une erreur programmés."""

    state: str = "state-xyz"
    finish_error: Exception | None = None
    start_error: Exception | None = None
    calls: list[tuple[str, Any]] = field(default_factory=list)

    def start(
        self,
        base_url: str,
        client_id: str,
        redirect_uri: str,
        permissions: int,
        ttl_days: int | None,
    ) -> tuple[str, ConnectState]:
        self.calls.append(("start", (base_url, client_id, redirect_uri, permissions, ttl_days)))
        if self.start_error:
            raise self.start_error
        pending = ConnectState(
            base_url=base_url,
            client_id=client_id,
            redirect_uri=redirect_uri,
            state=self.state,
            code_verifier="verifier-secret",
            private_jwk={"kty": "EC", "d": "cle-privee-secrete"},
        )
        return f"{base_url}/connect?request_uri=urn:x", pending

    def finish(self, pending: ConnectState, *, code: str, state: str) -> Any:
        self.calls.append(("finish", (pending.code_verifier, code, state)))
        if self.finish_error:
            raise self.finish_error

        @dataclass
        class _Result:
            token: str = TOKEN
            api_key_id: UUID = API_KEY_ID
            wallet_id: UUID = field(default_factory=uuid4)

        return _Result()


@pytest.fixture
async def pool(session_pool: asyncpg.Pool, monkeypatch) -> asyncpg.Pool:
    monkeypatch.setenv("RAG_MASTER_KEY", "x" * 64)
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5432/db")
    monkeypatch.setenv("RAG_POSTGRES_ADMIN_URL", "postgresql://u:p@localhost:5432/postgres")
    monkeypatch.setenv("RAG_PUBLIC_URL", "http://localhost:8000")
    monkeypatch.setenv("HARPOCRATE_DEK", "passphrase-of-at-least-32-characters-long")
    await run_migrations(session_pool, MIGRATIONS_DIR)
    await session_pool.execute("DELETE FROM harpocrate_vaults")
    return session_pool


def _service(fake: FakeHarpocrate) -> HarpocrateConnectService:
    settings = Settings()
    return HarpocrateConnectService(
        settings, HarpocrateVaultsService(settings), sdk_start=fake.start, sdk_finish=fake.finish
    )


def _identity(**over: Any) -> VaultIdentity:
    data = {
        "name": "rag-connect",
        "label": "Coffre connecté",
        "base_url": "https://vault.example",
        "is_default": False,
    }
    data.update(over)
    return VaultIdentity(**data)


async def _start(svc: HarpocrateConnectService, conn: asyncpg.Connection) -> str:
    started = await svc.resolve_start(
        conn, identity=_identity(), owner_id=OWNER, redirect_uri=REDIRECT
    )
    return started.binding_token


async def _callback(
    svc, conn, binding, *, owner=OWNER, state="state-xyz", code="code-1", error=None
):
    return await svc.resolve_callback(
        conn, owner_id=owner, binding_token=binding, state=state, code=code, error=error
    )


async def test_start_requests_27_permissions_and_stores_state_encrypted(pool) -> None:
    fake = FakeHarpocrate()
    async with pool.acquire() as conn:
        started = await _service(fake).resolve_start(
            conn, identity=_identity(), owner_id=OWNER, redirect_uri=REDIRECT
        )
        raw = await conn.fetchval(
            "SELECT encode(connect_state_encrypted, 'escape') FROM harpocrate_connect_requests"
        )
    assert started.browser_url.startswith("https://vault.example/connect?")
    assert fake.calls[0] == ("start", ("https://vault.example", "ragflow", REDIRECT, 27, 365))
    assert CONNECT_PERMISSIONS == 27
    # Ni le code_verifier ni la clé privée ne sont lisibles en base.
    assert "verifier-secret" not in raw
    assert "cle-privee-secrete" not in raw
    assert "binding" not in repr(started)


async def test_callback_nominal_creates_vault_with_obtained_key(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        vault = await _callback(svc, conn, binding)
        stored = await conn.fetchval(
            "SELECT pgp_sym_decrypt(api_key_encrypted, $1)::text FROM harpocrate_vaults "
            "WHERE id = $2",
            "passphrase-of-at-least-32-characters-long",
            vault.id,
        )
    assert (vault.name, vault.label, vault.base_url) == (
        "rag-connect",
        "Coffre connecté",
        "https://vault.example",
    )
    assert vault.api_key_id == str(API_KEY_ID)
    assert vault.owner_id == OWNER
    assert stored == TOKEN
    assert fake.calls[1] == ("finish", ("verifier-secret", "code-1", "state-xyz"))


async def test_callback_denied_consumes_request_and_creates_nothing(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, binding, code=None, error="access_denied")
        assert exc.value.reason == "denied"
        assert await conn.fetchval("SELECT count(*) FROM harpocrate_vaults") == 0
    assert [c[0] for c in fake.calls] == ["start"]


@pytest.mark.parametrize(
    ("binding_override", "owner"),
    [("autre-navigateur", OWNER), (None, OWNER), ("__same__", OTHER_OWNER)],
)
async def test_callback_foreign_session_refused_without_calling_harpocrate(
    pool, binding_override, owner
) -> None:
    """Liaison absente, d'un autre navigateur ou d'un autre admin : refus."""
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        presented = binding if binding_override == "__same__" else binding_override
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, presented, owner=owner)
        assert exc.value.reason == "state_unknown"
        assert await conn.fetchval("SELECT count(*) FROM harpocrate_vaults") == 0
    assert [c[0] for c in fake.calls] == ["start"]


async def test_callback_replay_reports_already_used_and_creates_one_vault(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        await _callback(svc, conn, binding)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, binding)
        assert exc.value.reason == "already_used"
        assert await conn.fetchval("SELECT count(*) FROM harpocrate_vaults") == 1
    assert [c[0] for c in fake.calls] == ["start", "finish"]


async def test_callback_expired_request_refused(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        await conn.execute(
            "UPDATE harpocrate_connect_requests SET expires_at = now() - interval '1 second'"
        )
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, binding)
    assert exc.value.reason == "state_unknown"


@pytest.mark.parametrize(
    ("error", "reason"),
    [
        (ConnectError("invalid_grant"), "exchange_failed"),
        (ConnectError("invalid_seal"), "exchange_failed"),
        (httpx.ConnectError("down"), "harpocrate_unreachable"),
    ],
)
async def test_callback_exchange_failure_saves_nothing(pool, error, reason) -> None:
    fake = FakeHarpocrate(finish_error=error)
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, binding)
        assert exc.value.reason == reason
        assert await conn.fetchval("SELECT count(*) FROM harpocrate_vaults") == 0


async def test_callback_name_taken_meanwhile_says_key_not_saved(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        binding = await _start(svc, conn)
        await conn.execute(_INSERT_TAKEN_NAME)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(svc, conn, binding)
    assert exc.value.reason == "name_taken_key_not_saved"


async def test_start_refuses_taken_name_and_http_url_without_calling_harpocrate(pool) -> None:
    fake = FakeHarpocrate()
    svc = _service(fake)
    async with pool.acquire() as conn:
        await conn.execute(_INSERT_TAKEN_NAME)
        with pytest.raises(ConnectFlowError) as taken:
            await svc.resolve_start(
                conn, identity=_identity(), owner_id=OWNER, redirect_uri=REDIRECT
            )
        with pytest.raises(ConnectFlowError) as insecure:
            await svc.resolve_start(
                conn,
                identity=_identity(name="autre", base_url="http://vault.example"),
                owner_id=OWNER,
                redirect_uri=REDIRECT,
            )
    assert (taken.value.reason, insecure.value.reason) == ("name_taken", "https_required")
    assert fake.calls == []


async def test_start_undeclared_app_reports_app_not_declared(pool) -> None:
    fake = FakeHarpocrate(start_error=ConnectError("invalid_redirect_uri"))
    async with pool.acquire() as conn:
        with pytest.raises(ConnectFlowError) as exc:
            await _start(_service(fake), conn)
        assert exc.value.reason == "app_not_declared"
        assert await conn.fetchval("SELECT count(*) FROM harpocrate_connect_requests") == 0
