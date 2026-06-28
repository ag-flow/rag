from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LocalLoginRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=1, max_length=255)
    password: str = Field(..., min_length=1, max_length=512)


class LocalLoginResponse(BaseModel):
    ok: bool = True


class AuthMethodsResponse(BaseModel):
    oidc_configured: bool
    local_auth_enabled: bool
    needs_setup: bool


class InitAdminRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    username: str = Field(..., min_length=1, max_length=255)
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=512)


class InitAdminResponse(BaseModel):
    ok: bool = True


class SetupStatusResponse(BaseModel):
    needs_setup: bool
