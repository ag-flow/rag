from __future__ import annotations

from pydantic import BaseModel


class WebhookHeaderIn(BaseModel):
    name: str
    value: str | None = None
    vault: str | None = None
    enabled: bool = True


class WebhookHeaderOut(BaseModel):
    id: str
    name: str
    value: None = None       # jamais retourné
    vault_ref: str | None
    enabled: bool


class WebhookOut(BaseModel):
    id: str
    name: str
    url: str
    enabled: bool
    headers: list[WebhookHeaderOut]


class WebhookCreateRequest(BaseModel):
    name: str
    url: str
    enabled: bool = True
    headers: list[WebhookHeaderIn] = []


class WebhookPatchRequest(BaseModel):
    name: str | None = None
    url: str | None = None
    enabled: bool | None = None


class WebhookHeaderPatchRequest(BaseModel):
    value: str | None = None
    vault: str | None = None
    enabled: bool | None = None


class WebhookCallOut(BaseModel):
    id: str
    webhook_id: str
    webhook_name: str
    correlation_id: str
    triggered_by: str
    webhook_url: str
    http_status: int | None
    error: str | None
    duration_ms: int | None
    called_at: str
    success: bool
