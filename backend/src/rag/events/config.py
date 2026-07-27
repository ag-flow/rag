"""Config singleton du producteur d'events (table `events_producer_config`).

Lue à chaud à l'émission ET par le worker → le toggle `enabled` et la liste
blanche `events` prennent effet immédiatement, sans redémarrage.
"""

from __future__ import annotations

from dataclasses import dataclass

import asyncpg


@dataclass(frozen=True)
class EventsProducerConfig:
    enabled: bool
    workflow_base_url: str
    source_id: str
    secret_ref: str
    source_uri: str
    events: list[str]  # liste blanche des event_codes relayés

    def relays(self, event_code: str) -> bool:
        """Vrai si l'event doit être relayé (activé ET dans la liste blanche)."""
        return self.enabled and event_code in self.events

    def is_deliverable(self) -> bool:
        """Config suffisante pour signer/poster (URL + source + secret)."""
        return bool(self.workflow_base_url and self.source_id and self.secret_ref)


async def get_config(conn: asyncpg.Connection) -> EventsProducerConfig:
    row = await conn.fetchrow(
        "SELECT enabled, workflow_base_url, source_id, secret_ref, source_uri, events "
        "FROM events_producer_config WHERE id = 1"
    )
    if row is None:  # pragma: no cover — la migration seed la ligne
        return EventsProducerConfig(False, "", "", "", "urn:yoops:rag", [])
    return EventsProducerConfig(
        enabled=row["enabled"],
        workflow_base_url=row["workflow_base_url"],
        source_id=row["source_id"],
        secret_ref=row["secret_ref"],
        source_uri=row["source_uri"],
        events=list(row["events"]),
    )


async def put_config(
    conn: asyncpg.Connection,
    *,
    enabled: bool,
    workflow_base_url: str,
    source_id: str,
    secret_ref: str,
    source_uri: str,
    events: list[str],
) -> EventsProducerConfig:
    await conn.execute(
        """
        UPDATE events_producer_config
        SET enabled=$1, workflow_base_url=$2, source_id=$3, secret_ref=$4,
            source_uri=$5, events=$6, updated_at=now()
        WHERE id = 1
        """,
        enabled,
        workflow_base_url,
        source_id,
        secret_ref,
        source_uri,
        events,
    )
    return await get_config(conn)
