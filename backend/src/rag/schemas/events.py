from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EventsProducerSpec(BaseModel):
    """Payload PUT /api/admin/events-producer."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = False
    workflow_base_url: str = Field(default="", max_length=512)
    source_id: str = Field(default="", max_length=128)
    secret_ref: str = Field(default="", max_length=512)
    source_uri: str = Field(default="urn:yoops:rag", max_length=256)
    events: list[str] = Field(default_factory=list)


class EventsProducerResponse(BaseModel):
    enabled: bool
    workflow_base_url: str
    source_id: str
    secret_ref: str
    source_uri: str
    events: list[str]
    # Codes d'events émissibles par rag (aide l'IHM à composer la liste blanche).
    known_events: list[str]


class TestConnectionResponse(BaseModel):
    ok: bool
    status_code: int
    detail: str
