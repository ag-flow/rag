"""Egress (202=succès), test-envelope, et émission gouvernée par la config."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import httpx

from rag.events.config import EventsProducerConfig
from rag.events.egress import build_test_envelope, deliver
from rag.events.registry import WORKSPACE_CREATED, workspace_created


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestDeliver:
    async def test_202_is_delivered(self) -> None:
        captured = {}

        def handler(request: httpx.Request) -> httpx.Response:
            captured["url"] = str(request.url)
            captured["sig"] = request.headers.get("x-signature")
            captured["body"] = request.content
            return httpx.Response(202)

        async with _client(handler) as client:
            res = await deliver(
                client,
                base_url="https://wf.example",
                source_id="src-1",
                secret="k",
                raw_body=b'{"_eventId":"x"}',
            )
        assert res.delivered is True and res.status_code == 202
        assert captured["url"] == "https://wf.example/events/src-1"
        assert len(captured["sig"]) == 64  # hex nu
        assert captured["body"] == b'{"_eventId":"x"}'  # octets postés = octets signés

    async def test_non_202_is_not_delivered(self) -> None:
        async with _client(lambda r: httpx.Response(401)) as client:
            res = await deliver(
                client, base_url="https://wf", source_id="s", secret="k", raw_body=b"{}"
            )
        assert res.delivered is False and res.status_code == 401

    async def test_transport_error_is_not_delivered(self) -> None:
        def boom(_r: httpx.Request) -> httpx.Response:
            raise httpx.ConnectError("down")

        async with _client(boom) as client:
            res = await deliver(
                client, base_url="https://wf", source_id="s", secret="k", raw_body=b"{}"
            )
        assert res.delivered is False and res.status_code == 0


def test_build_test_envelope_uses_uncatalogued_code() -> None:
    raw = build_test_envelope("urn:yoops:rag")
    env = json.loads(raw)
    assert env["_eventCode"] == "rag.testevent.v1"


class TestConfigRelays:
    def _cfg(self, *, enabled: bool, events: list[str]) -> EventsProducerConfig:
        return EventsProducerConfig(
            enabled=enabled,
            workflow_base_url="https://wf",
            source_id="s",
            secret_ref="${vault://rag:hmac}",
            source_uri="urn:yoops:rag",
            events=events,
        )

    def test_relays_only_when_enabled_and_whitelisted(self) -> None:
        assert self._cfg(enabled=True, events=[WORKSPACE_CREATED]).relays(WORKSPACE_CREATED)
        assert not self._cfg(enabled=False, events=[WORKSPACE_CREATED]).relays(WORKSPACE_CREATED)
        assert not self._cfg(enabled=True, events=[]).relays(WORKSPACE_CREATED)


class TestEmit:
    async def test_emit_enqueues_only_when_relayed(self, monkeypatch) -> None:
        from rag.events import emit

        # Config qui relaie l'event.
        cfg = EventsProducerConfig(
            enabled=True,
            workflow_base_url="https://wf",
            source_id="s",
            secret_ref="r",
            source_uri="urn:yoops:rag",
            events=[WORKSPACE_CREATED],
        )
        monkeypatch.setattr(emit, "get_config", AsyncMock(return_value=cfg))
        enqueue = AsyncMock()
        monkeypatch.setattr(emit.workflow_outbox, "enqueue", enqueue)

        pool = MagicMock()
        conn = MagicMock()
        conn.transaction = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=None), __aexit__=AsyncMock(return_value=False)
            )
        )
        pool.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=conn), __aexit__=AsyncMock(return_value=False)
            )
        )

        ev = workspace_created(
            name="d", label="D", slug="d", owner_id=None, occurred_at=datetime.now(UTC)
        )
        await emit.emit_workflow_event(pool, ev)
        enqueue.assert_awaited_once()

    async def test_emit_never_raises_on_error(self, monkeypatch) -> None:
        from rag.events import emit

        monkeypatch.setattr(emit, "get_config", AsyncMock(side_effect=RuntimeError("db down")))
        pool = MagicMock()
        pool.acquire = MagicMock(
            return_value=MagicMock(
                __aenter__=AsyncMock(return_value=MagicMock()),
                __aexit__=AsyncMock(return_value=False),
            )
        )
        ev = workspace_created(
            name="d", label="D", slug="d", owner_id=None, occurred_at=datetime.now(UTC)
        )
        # Ne doit PAS lever (fire-and-forget).
        await emit.emit_workflow_event(pool, ev)
