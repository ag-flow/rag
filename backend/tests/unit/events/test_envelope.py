"""Invariants de l'enveloppe Porte A (déterminisme, tz-aware, signer=poster)."""

from __future__ import annotations

import hmac
import json
from datetime import UTC, datetime
from hashlib import sha256

import pytest

from rag.events.envelope import serialize, sign, to_envelope
from rag.events.registry import WORKSPACE_CREATED, AppEvent, workspace_created

_TS = datetime(2026, 7, 20, 8, 12, 0, tzinfo=UTC)


def _event() -> AppEvent:
    return workspace_created(
        name="docs", label="Docs", slug="docs", owner_id="o1", occurred_at=_TS
    )


class TestEnvelope:
    def test_five_system_fields_and_flat_subject(self) -> None:
        env = to_envelope(_event(), source_uri="urn:yoops:rag")
        assert env["_eventCode"] == WORKSPACE_CREATED
        assert env["_occurredAt"] == "2026-07-20T08:12:00+00:00"
        assert env["_source"] == "urn:yoops:rag"
        assert env["_specVersion"] == "1.0"
        # métier à plat, pas de wrapper `data`
        assert env["slug"] == "docs" and env["label"] == "Docs"

    def test_event_id_is_deterministic(self) -> None:
        a = to_envelope(_event(), source_uri="urn:yoops:rag")["_eventId"]
        b = to_envelope(_event(), source_uri="urn:yoops:rag")["_eventId"]
        assert a == b  # même clé de dédup → même UUID (rejeu idempotent)

    def test_naive_datetime_rejected(self) -> None:
        naive = AppEvent(
            event_code="rag.x.y.v1",
            occurred_at=datetime(2026, 7, 20, 8, 0, 0),
            subject={"a": 1},
            dedup_key="k",
        )
        with pytest.raises(ValueError, match="tz-aware"):
            to_envelope(naive, source_uri="urn:yoops:rag")

    def test_business_key_with_underscore_rejected(self) -> None:
        bad = AppEvent(
            event_code="rag.x.y.v1", occurred_at=_TS, subject={"_eventId": "x"}, dedup_key="k"
        )
        with pytest.raises(ValueError, match="préfixe système"):
            to_envelope(bad, source_uri="urn:yoops:rag")


class TestSerializeAndSign:
    def test_serialize_is_stable_and_compact(self) -> None:
        env = to_envelope(_event(), source_uri="urn:yoops:rag")
        raw1 = serialize(env)
        raw2 = serialize(env)
        assert raw1 == raw2
        assert b", " not in raw1 and b": " not in raw1  # separators compacts

    def test_sign_matches_hmac_of_exact_bytes(self) -> None:
        env = to_envelope(_event(), source_uri="urn:yoops:rag")
        raw = serialize(env)
        expected = hmac.new(b"shared-secret", raw, sha256).hexdigest()
        assert sign("shared-secret", raw) == expected
        assert len(sign("shared-secret", raw)) == 64  # hex nu, sans préfixe

    def test_signed_bytes_are_the_posted_bytes(self) -> None:
        # Garantit qu'on ne re-sérialise pas : signer json.loads(raw) puis
        # re-dump donnerait des octets différents.
        env = to_envelope(_event(), source_uri="urn:yoops:rag")
        raw = serialize(env)
        reparsed = json.dumps(json.loads(raw)).encode()  # sérialisation "naïve"
        assert reparsed != raw  # espaces différents → signature différente
