from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class OidcConfigCreate(BaseModel):
    """Body de `POST /admin/oidc`.

    Le client secret n'est pas ici : il se configure dans le .env
    (`RAG_OIDC_CLIENT_SECRET`), jamais stocké en base.
    """

    model_config = ConfigDict(extra="forbid")

    issuer: HttpUrl
    client_id: str = Field(..., min_length=1, max_length=255)


class OidcConfigRead(BaseModel):
    """Réponse de `GET/POST /admin/oidc`."""

    issuer: str
    client_id: str


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
