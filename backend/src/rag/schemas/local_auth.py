from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class LocalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=512)


class LocalLoginResponse(BaseModel):
    ok: bool = True


class AuthMethodsResponse(BaseModel):
    oidc_configured: bool
    bootstrap_enabled: bool
