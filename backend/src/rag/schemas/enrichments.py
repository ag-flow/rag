from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PromptTemplateCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=128)
    language: str = Field(min_length=1, max_length=64)
    description: str | None = None
    metadata_key: str = Field(min_length=1, max_length=64)
    result_type: str = Field(default="text")
    result_schema: dict[str, Any] | None = None
    prompt: str = Field(min_length=1)


class PromptTemplatePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str | None = None
    prompt: str | None = None
    result_schema: dict[str, Any] | None = None


class PromptTemplateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    language: str
    description: str | None
    metadata_key: str
    result_type: str
    result_schema: dict[str, Any] | None
    prompt: str
    created_at: datetime
    updated_at: datetime


class TriggerCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    extension: str = Field(min_length=2, max_length=16)
    enabled: bool = True


class TriggerPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class TriggerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    extension: str
    enabled: bool
    created_at: datetime


class TriggerPromptCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    template_id: UUID
    llm_id: UUID
    order_index: int = Field(ge=1)
    enabled: bool = True


class TriggerPromptPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    order_index: int | None = Field(default=None, ge=1)


class TriggerPromptOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    template_id: UUID
    template_name: str
    llm_id: UUID
    llm_provider: str
    llm_model: str
    order_index: int
    enabled: bool
