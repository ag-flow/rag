"""« Reconnecter » un coffre existant (ticket c3cf13e2).

Harpocrate est simulé (doublures du test « Connecter ») ; le wallet ouvert par
la clé ACTUELLE l'est par une sonde programmable. La base est réelle, pour
éprouver le remplacement chiffré, la tenue en attente et la décision unique.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import asyncpg
import httpx
import pytest
from harpocrate.exceptions import ConnectError, VaultHttpError

from rag.config import Settings
from rag.schemas.harpocrate_vaults import VaultCreateRequest, VaultSummary
from rag.services.harpocrate_connect import HarpocrateConnectService
from rag.services.harpocrate_connect_common import ConnectFlowError
from rag.services.harpocrate_vaults import HarpocrateVaultsService
from tests.integration.test_harpocrate_connect_service import (
    API_KEY_ID,
    OTHER_OWNER,
    OWNER,
    REDIRECT,
    FakeHarpocrate,
    pool,  # noqa: F401 — fixture partagée (migrations + DEK)
)

DEK = "passphrase-of-at-least-32-characters-long"
OLD_KEY = "hrpv_1_ancienne-cle-du-coffre"
NEW_KEY = "hrpv_1_nouvelle-cle-obtenue"
WALLET = UUID("aaaaaaaa-0000-0000-0000-000000000001")
OTHER_WALLET = UUID("bbbbbbbb-0000-0000-0000-000000000002")
_STORED_KEY = (
    "SELECT api_key_id, pgp_sym_decrypt(api_key_encrypted, $1)::text AS key "
    "FROM harpocrate_vaults WHERE id = $2"
)


@dataclass
class FakeWalletProbe:
    """Sonde du wallet de la clé actuelle : un wallet, ou une erreur."""

    wallet: UUID | None = WALLET
    error: Exception | None = None
    calls: list[tuple[str, str]] = field(default_factory=list)

    def __call__(self, base_url: str, token: str) -> str:
        self.calls.append((base_url, token))
        if self.error is not None:
            raise self.error
        return str(self.wallet)


@dataclass
class FakeValuesCache:
    cleared: int = 0

    def clear_cache(self) -> None:
        self.cleared += 1


@dataclass
class Rig:
    svc: HarpocrateConnectService
    vaults: HarpocrateVaultsService
    harpocrate: FakeHarpocrate
    probe: FakeWalletProbe
    values_cache: FakeValuesCache


def _rig(*, new_wallet: UUID = WALLET, probe: FakeWalletProbe | None = None) -> Rig:
    settings = Settings()
    vaults = HarpocrateVaultsService(settings)
    cache = FakeValuesCache()
    vaults.bind_resolved_values_cache(cache)
    fake = FakeHarpocrate(wallet_id=new_wallet, token=NEW_KEY)
    probe = probe or FakeWalletProbe()
    svc = HarpocrateConnectService(
        settings, vaults, sdk_start=fake.start, sdk_finish=fake.finish, wallet_probe=probe
    )
    return Rig(svc, vaults, fake, probe, cache)


async def _vault(rig: Rig, conn: asyncpg.Connection) -> VaultSummary:
    req = VaultCreateRequest(
        name="rag-existant",
        label="Coffre existant",
        base_url="https://vault.example",
        api_key_id="k-ancienne",
        api_key=OLD_KEY,
    )
    return await rig.vaults.create(conn, req, owner_id=OWNER)


async def _start(rig: Rig, conn: asyncpg.Connection, vault: VaultSummary) -> str:
    started = await rig.svc.resolve_reconnect_start(
        conn, vault=vault, owner_id=OWNER, redirect_uri=REDIRECT
    )
    return started.binding_token


async def _callback(rig: Rig, conn: asyncpg.Connection, binding: str, **over: Any) -> Any:
    args: dict[str, Any] = {
        "owner_id": OWNER,
        "binding_token": binding,
        "state": rig.harpocrate.state,
        "code": "code-1",
        "error": None,
    }
    args.update(over)
    return await rig.svc.resolve_callback(conn, **args)


async def _stored(conn: asyncpg.Connection, vault_id: UUID) -> tuple[str, str]:
    row = await conn.fetchrow(_STORED_KEY, DEK, vault_id)
    return row["api_key_id"], row["key"]


async def _pending_outcome(rig: Rig, conn: asyncpg.Connection) -> tuple[VaultSummary, Any]:
    vault = await _vault(rig, conn)
    outcome = await _callback(rig, conn, await _start(rig, conn, vault))
    assert outcome.kind == "confirm_wallet"
    return vault, outcome


def _decision(outcome: Any, **over: Any) -> dict[str, Any]:
    args = {
        "request_id": outcome.pending_request_id,
        "confirm_token": outcome.confirm_token,
        "owner_id": OWNER,
    }
    args.update(over)
    return args


async def test_reconnect_start_targets_vault_with_same_client_and_permissions(pool) -> None:
    rig = _rig()
    async with pool.acquire() as conn:
        vault = await _vault(rig, conn)
        await _start(rig, conn, vault)
        target = await conn.fetchval("SELECT vault_id FROM harpocrate_connect_requests")
    assert target == vault.id
    assert rig.harpocrate.calls[0] == (
        "start",
        ("https://vault.example", "ragflow", REDIRECT, 27, 365),
    )


async def test_reconnect_same_wallet_replaces_key_and_clears_caches(pool) -> None:
    rig = _rig()
    async with pool.acquire() as conn:
        vault = await _vault(rig, conn)
        cleared_before = rig.values_cache.cleared
        outcome = await _callback(rig, conn, await _start(rig, conn, vault))
        stored = await _stored(conn, vault.id)
    assert outcome.kind == "rotated"
    assert outcome.vault.api_key_id == str(API_KEY_ID)
    assert stored == (str(API_KEY_ID), NEW_KEY)
    # Le wallet actuel a été lu avec l'ANCIENNE clé, à l'URL du coffre.
    assert rig.probe.calls == [("https://vault.example", OLD_KEY)]
    assert rig.values_cache.cleared == cleared_before + 1


async def test_reconnect_other_wallet_holds_key_until_confirmed(pool) -> None:
    rig = _rig(new_wallet=OTHER_WALLET)
    async with pool.acquire() as conn:
        vault, outcome = await _pending_outcome(rig, conn)
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)
        raw = await conn.fetchval(
            "SELECT encode(pending_key_encrypted, 'escape') FROM harpocrate_connect_requests"
        )
        assert NEW_KEY not in raw
        pending = await rig.svc.reconnect.db_get_pending(conn, **_decision(outcome))
        assert (pending.previous_wallet_id, pending.new_wallet_id) == (WALLET, OTHER_WALLET)
        assert pending.vault_id == vault.id

        confirmed = await rig.svc.reconnect.resolve_confirm(conn, **_decision(outcome))
        assert confirmed.api_key_id == str(API_KEY_ID)
        assert await _stored(conn, vault.id) == (str(API_KEY_ID), NEW_KEY)
        # La clé tenue en attente est effacée dès la décision.
        assert await conn.fetchval(
            "SELECT pending_key_encrypted FROM harpocrate_connect_requests"
        ) is None


async def test_reconnect_other_wallet_refused_keeps_old_key(pool) -> None:
    rig = _rig(new_wallet=OTHER_WALLET)
    async with pool.acquire() as conn:
        vault, outcome = await _pending_outcome(rig, conn)
        await rig.svc.reconnect.resolve_cancel(conn, **_decision(outcome))
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)
        with pytest.raises(ConnectFlowError) as exc:
            await rig.svc.reconnect.resolve_confirm(conn, **_decision(outcome))
        assert exc.value.reason == "already_used"
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)


async def test_reconnect_confirm_replay_reports_already_used(pool) -> None:
    rig = _rig(new_wallet=OTHER_WALLET)
    async with pool.acquire() as conn:
        _vault_row, outcome = await _pending_outcome(rig, conn)
        await rig.svc.reconnect.resolve_confirm(conn, **_decision(outcome))
        with pytest.raises(ConnectFlowError) as exc:
            await rig.svc.reconnect.resolve_confirm(conn, **_decision(outcome))
    assert exc.value.reason == "already_used"


@pytest.mark.parametrize(
    "error",
    [VaultHttpError(401, "expired"), httpx.ConnectError("down")],
)
async def test_reconnect_unverifiable_current_wallet_asks_confirmation(pool, error) -> None:
    """Clé actuelle muette (révoquée, Harpocrate injoignable) : on ne devine pas."""
    rig = _rig(probe=FakeWalletProbe(error=error))
    async with pool.acquire() as conn:
        vault, outcome = await _pending_outcome(rig, conn)
        pending = await rig.svc.reconnect.db_get_pending(conn, **_decision(outcome))
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)
    assert pending.previous_wallet_id is None
    assert pending.new_wallet_id == WALLET


@pytest.mark.parametrize(
    "over",
    [
        {"confirm_token": "autre-navigateur"},
        {"confirm_token": None},
        {"owner_id": OTHER_OWNER},
        {"request_id": uuid4()},
    ],
)
async def test_reconnect_decision_from_foreign_session_refused(pool, over) -> None:
    rig = _rig(new_wallet=OTHER_WALLET)
    async with pool.acquire() as conn:
        vault, outcome = await _pending_outcome(rig, conn)
        for decide in (rig.svc.reconnect.resolve_confirm, rig.svc.reconnect.resolve_cancel):
            with pytest.raises(ConnectFlowError) as exc:
                await decide(conn, **_decision(outcome, **over))
            assert exc.value.reason == "state_unknown"
        with pytest.raises(ConnectFlowError):
            await rig.svc.reconnect.db_get_pending(conn, **_decision(outcome, **over))
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)


async def test_reconnect_confirm_after_expiry_refused(pool) -> None:
    rig = _rig(new_wallet=OTHER_WALLET)
    async with pool.acquire() as conn:
        vault, outcome = await _pending_outcome(rig, conn)
        await conn.execute(
            "UPDATE harpocrate_connect_requests SET expires_at = now() - interval '1 second'"
        )
        with pytest.raises(ConnectFlowError) as exc:
            await rig.svc.reconnect.resolve_confirm(conn, **_decision(outcome))
        assert exc.value.reason == "state_unknown"
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)


@pytest.mark.parametrize(
    ("over", "harpocrate_error", "reason"),
    [
        ({"code": None, "error": "access_denied"}, None, "denied"),
        ({}, ConnectError("invalid_grant"), "exchange_failed"),
        ({"state": "state-etranger"}, None, "state_unknown"),
    ],
)
async def test_reconnect_refusal_or_failure_keeps_old_key(
    pool, over, harpocrate_error, reason
) -> None:
    rig = _rig()
    rig.harpocrate.finish_error = harpocrate_error
    async with pool.acquire() as conn:
        vault = await _vault(rig, conn)
        binding = await _start(rig, conn, vault)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(rig, conn, binding, **over)
        assert exc.value.reason == reason
        assert await _stored(conn, vault.id) == ("k-ancienne", OLD_KEY)


async def test_reconnect_callback_replay_rotates_once(pool) -> None:
    rig = _rig()
    async with pool.acquire() as conn:
        vault = await _vault(rig, conn)
        binding = await _start(rig, conn, vault)
        await _callback(rig, conn, binding)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(rig, conn, binding)
    assert exc.value.reason == "already_used"
    assert [c[0] for c in rig.harpocrate.calls] == ["start", "finish"]


async def test_reconnect_vault_deleted_meanwhile_saves_nothing(pool) -> None:
    rig = _rig()
    async with pool.acquire() as conn:
        vault = await _vault(rig, conn)
        binding = await _start(rig, conn, vault)
        await rig.vaults.delete(conn, vault.id)
        with pytest.raises(ConnectFlowError) as exc:
            await _callback(rig, conn, binding)
    # La demande a disparu avec le coffre (ON DELETE CASCADE).
    assert exc.value.reason == "state_unknown"
    assert [c[0] for c in rig.harpocrate.calls] == ["start"]
