from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OidcConfigCreate(BaseModel):
    """Body de `POST /admin/oidc`. Le `client_secret_ref` est juste la clé
    logique Harpocrate — jamais le secret en clair."""

    model_config = ConfigDict(extra="forbid")

    issuer: HttpUrl
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret_ref: str = Field(..., min_length=1, max_length=255)


class OidcConfigRead(BaseModel):
    """Réponse de `GET/POST /admin/oidc`."""

    issuer: str
    client_id: str
    client_secret_ref: str


class MeResponse(BaseModel):
    """Réponse de `GET /me`."""

    sub: str
    email: str | None
    name: str | None
    roles: list[str]


@dataclass(frozen=True)
class OidcUserContext:
    """Retourné par la dependency `require_oidc_role`.

    Frozen : empêche un endpoint de muter le contexte par accident.
    """

    sub: str
    email: str | None
    name: str | None
    roles: list[str]
