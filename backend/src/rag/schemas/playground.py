from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

LlmProvider = Literal["claude", "openai", "azure-openai", "ollama"]


class LlmConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: LlmProvider
    model: str = Field(min_length=1, max_length=128)
    base_url: str | None = None
    api_key_ref: str | None = None
    enabled: bool = True


class LlmConfigPatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool


class LlmConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    provider: str
    model: str
    base_url: str | None
    api_key_ref: str | None
    enabled: bool
    created_at: datetime


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatLlmSpec(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider: str
    model: str


class PlaygroundChatRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    message: str = Field(min_length=1)
    history: list[ChatMessage] = Field(default_factory=list)
    llm: ChatLlmSpec
    top_k: int = Field(default=5, ge=1, le=50)
    min_score: float = Field(default=0.7, ge=0.0, le=1.0)


class ChunkResult(BaseModel):
    path: str
    chunk_index: int
    content: str
    score: float


class UsageInfo(BaseModel):
    prompt_tokens: int
    completion_tokens: int


class PlaygroundChatResponse(BaseModel):
    message: str
    answer: str
    chunks: list[ChunkResult]
    usage: UsageInfo
