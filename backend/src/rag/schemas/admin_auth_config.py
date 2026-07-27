from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ClientSecretStatus(BaseModel):
    """Indique si un client secret OIDC est défini — jamais sa valeur."""

    configured: bool


class ClientSecretSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: str = Field(..., min_length=1, max_length=2048)

    @field_validator("value")
    @classmethod
    def _no_newline(cls, v: str) -> str:
        if "\n" in v or "\r" in v:
            raise ValueError("le client secret ne doit pas contenir de saut de ligne")
        return v


class PublicUrlState(BaseModel):
    """URL publique fixée depuis l'IHM — null = dérivée de l'adresse d'appel."""

    value: str | None


class PublicUrlSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # "" = retour au défaut (URL dérivée de l'adresse du client).
    value: str = Field(..., max_length=2048)

    @field_validator("value")
    @classmethod
    def _http_url_or_empty(cls, v: str) -> str:
        v = v.strip()
        if v and not (v.startswith("https://") or v.startswith("http://")):
            raise ValueError("l'URL publique doit commencer par http:// ou https://")
        if "\n" in v or "\r" in v or " " in v:
            raise ValueError("URL publique invalide")
        return v


class LocalLoginState(BaseModel):
    """`enabled=True` ⇒ connexion locale autorisée."""

    enabled: bool


class LocalLoginSet(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool
