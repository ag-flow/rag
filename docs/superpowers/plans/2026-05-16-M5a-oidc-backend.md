# M5a — OIDC Backend (Keycloak) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer un flow OIDC Keycloak complet en backend (CRUD config + `/auth/login|callback|refresh|logout` + `/me` + dependency `require_oidc_role`) avec session cookie signé contenant id_token JWT + refresh_token, prêt à être consommé par l'IHM en M5b.

**Architecture:** `OidcService` encapsule la discovery (lazy + cache 1h), JWKS (cache + reload-on-fail), exchange_code / refresh via Authlib, verify JWT (signature + iss/aud/exp). Endpoints `/auth/*` orchestrent le flow OAuth2 avec state+nonce (CSRF + replay). Cookies signés via `SessionMiddleware` Starlette (clé `RAG_SESSION_SECRET` ≥32 chars, fallback `RAG_MASTER_KEY` en dev). Dependency `require_oidc_role(role)` valide le cookie, vérifie le JWT, extrait `resource_access.<client_id>.roles`, applique la hierarchy `rag-admin > rag-viewer`.

**Tech Stack:** FastAPI + Pydantic v2, `authlib>=1.3` (OAuth2 + JWT + JWKS), `starlette.middleware.sessions.SessionMiddleware`, asyncpg (pour `oidc_config`), httpx (mocké en tests), structlog.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/pyproject.toml` | **Modify** | Ajouter `authlib>=1.3,<2.0` aux dépendances |
| `backend/src/rag/config.py` | **Modify** | Ajouter `rag_session_secret: SecretStr` avec fallback master_key + validator ≥32 chars |
| `backend/src/rag/api/errors.py` | **Modify** | Ajouter 10 nouvelles classes : `OidcNotConfigured`, `OidcKeycloakUnreachable`, `OidcStateMissing`, `OidcStateMismatch`, `OidcInvalidCode`, `OidcSessionMissing`, `OidcInvalidSession`, `OidcSessionExpired`, `OidcInvalidToken`, `OidcRoleForbidden` |
| `backend/src/rag/schemas/oidc.py` | **Create** | `OidcConfigCreate`, `OidcConfigRead`, `MeResponse`, `OidcUserContext` dataclass |
| `backend/src/rag/services/oidc.py` | **Create** | `OidcConfig`/`_DiscoveryDoc`/`_TokenPair` dataclasses + `OidcService` : CRUD + discovery + JWKS + exchange_code + refresh + verify + extract_roles + build URLs |
| `backend/src/rag/auth/oidc_dependency.py` | **Create** | `require_oidc_role(role)` factory + `_role_grants` hierarchy + cookie session helpers |
| `backend/src/rag/api/admin_oidc.py` | **Create** | Router master-key : POST/GET `/admin/oidc` |
| `backend/src/rag/api/auth.py` | **Create** | Router IHM : `/auth/login`, `/auth/callback`, `/auth/refresh`, `/auth/logout`, `/me` |
| `backend/src/rag/main.py` | **Modify** | Imports + `app.state.oidc` + `SessionMiddleware` + include routers |
| `backend/tests/unit/services/test_oidc_config_service.py` | **Create** | Unit tests CRUD `oidc_config` |
| `backend/tests/unit/services/test_oidc_discovery.py` | **Create** | Unit tests discovery + JWKS (mocks httpx) |
| `backend/tests/unit/services/test_oidc_verify.py` | **Create** | Unit tests `verify_id_token` (clés RSA générées) |
| `backend/tests/unit/services/test_oidc_exchange.py` | **Create** | Unit tests `exchange_code` + `refresh` |
| `backend/tests/unit/services/test_oidc_roles.py` | **Create** | Unit tests `extract_roles` |
| `backend/tests/unit/services/test_oidc_authorize_url.py` | **Create** | Unit tests `build_authorize_url` + `build_logout_url` |
| `backend/tests/unit/auth/test_oidc_dependency.py` | **Create** | Unit tests `require_oidc_role` |
| `backend/tests/unit/schemas/test_oidc_dto.py` | **Create** | Unit tests DTOs |
| `backend/tests/unit/api/test_oidc_errors.py` | **Create** | Unit tests des 10 exceptions |
| `backend/tests/api/test_admin_oidc.py` | **Create** | Integration tests CRUD `/admin/oidc` |
| `backend/tests/api/test_auth_flow.py` | **Create** | Integration tests OAuth2 flow (Keycloak mocked) |
| `backend/tests/api/test_auth_errors.py` | **Create** | Integration tests codes erreurs |

---

## Task 1: Ajouter authlib aux dépendances

**Files:**
- Modify: `backend/pyproject.toml`

- [ ] **Step 1: Ajouter authlib à la liste des dépendances**

Dans `backend/pyproject.toml`, dans le bloc `dependencies = [...]`, ajouter une ligne :

```toml
    "authlib>=1.3,<2.0",
```

Position : juste après `"pgvector>=0.3",` pour grouper avec les autres deps applicatives.

- [ ] **Step 2: Installer la dépendance**

```powershell
cd backend
uv sync
```

Expected : `authlib==1.x.y` est installé dans le venv.

- [ ] **Step 3: Smoke import**

```powershell
uv run python -c "from authlib.integrations.httpx_client import AsyncOAuth2Client; from authlib.jose import jwt, JsonWebKey; print('OK')"
```

Expected : `OK`.

- [ ] **Step 4: Commit**

```powershell
git add backend/pyproject.toml backend/uv.lock
git commit -m "deps(M5a): authlib>=1.3 pour OAuth2/OIDC + JWT/JWKS"
```

---

## Task 2: Schemas DTOs

**Files:**
- Create: `backend/src/rag/schemas/oidc.py`
- Create: `backend/tests/unit/schemas/test_oidc_dto.py`

- [ ] **Step 1: Écrire les tests DTOs**

```python
# backend/tests/unit/schemas/test_oidc_dto.py
from __future__ import annotations

import pytest
from pydantic import ValidationError

from rag.schemas.oidc import (
    MeResponse,
    OidcConfigCreate,
    OidcConfigRead,
    OidcUserContext,
)


def test_oidc_config_create_accepts_valid_payload() -> None:
    cfg = OidcConfigCreate(
        issuer="https://keycloak.yoops.org/realms/homelab",
        client_id="rag-service",
        client_secret_ref="keycloak_rag_client_secret",
    )
    assert str(cfg.issuer) == "https://keycloak.yoops.org/realms/homelab"
    assert cfg.client_id == "rag-service"


def test_oidc_config_create_rejects_non_url_issuer() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="not-a-url",
            client_id="rag-service",
            client_secret_ref="x",
        )


def test_oidc_config_create_rejects_empty_client_id() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="",
            client_secret_ref="x",
        )


def test_oidc_config_create_rejects_empty_client_secret_ref() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="rag-service",
            client_secret_ref="",
        )


def test_oidc_config_create_rejects_extra_fields() -> None:
    with pytest.raises(ValidationError):
        OidcConfigCreate(
            issuer="https://keycloak.yoops.org/realms/homelab",
            client_id="rag-service",
            client_secret_ref="x",
            extra_field="rejected",
        )


def test_oidc_config_read_serializes_full() -> None:
    cfg = OidcConfigRead(
        issuer="https://keycloak.yoops.org/realms/homelab",
        client_id="rag-service",
        client_secret_ref="keycloak_rag_client_secret",
    )
    d = cfg.model_dump()
    assert d["issuer"] == "https://keycloak.yoops.org/realms/homelab"


def test_me_response_serializes_with_optional_fields() -> None:
    r = MeResponse(
        sub="user-uuid",
        email=None,
        name=None,
        roles=["rag-viewer"],
    )
    d = r.model_dump()
    assert d["email"] is None
    assert d["roles"] == ["rag-viewer"]


def test_oidc_user_context_is_frozen() -> None:
    import dataclasses
    ctx = OidcUserContext(sub="x", email=None, name=None, roles=[])
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.sub = "other"  # type: ignore[misc]
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
cd backend
uv run pytest tests/unit/schemas/test_oidc_dto.py -v
```

Expected : `ModuleNotFoundError: No module named 'rag.schemas.oidc'`.

- [ ] **Step 3: Créer `schemas/oidc.py`**

```python
# backend/src/rag/schemas/oidc.py
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
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/schemas/test_oidc_dto.py -v
```

Expected : `8 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/schemas/oidc.py tests/unit/schemas/test_oidc_dto.py
uv run ruff format src/rag/schemas/oidc.py tests/unit/schemas/test_oidc_dto.py
uv run mypy src/rag/schemas/oidc.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/schemas/oidc.py backend/tests/unit/schemas/test_oidc_dto.py
git commit -m "feat(M5a): schemas OIDC (OidcConfigCreate/Read, MeResponse, OidcUserContext)"
```

---

## Task 3: Exceptions OIDC dans errors.py

**Files:**
- Modify: `backend/src/rag/api/errors.py`
- Create: `backend/tests/unit/api/test_oidc_errors.py`

- [ ] **Step 1: Écrire les tests des nouvelles exceptions**

```python
# backend/tests/unit/api/test_oidc_errors.py
from __future__ import annotations

from rag.api.errors import (
    AdminError,
    OidcInvalidCode,
    OidcInvalidSession,
    OidcInvalidToken,
    OidcKeycloakUnreachable,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)


def test_oidc_not_configured_payload() -> None:
    e = OidcNotConfigured()
    assert isinstance(e, AdminError)
    assert e.http_status == 503
    assert e.to_payload() == {
        "error": "oidc_not_configured",
        "message": "POST /admin/oidc avec la master-key pour configurer Keycloak",
    }


def test_oidc_keycloak_unreachable_payload() -> None:
    e = OidcKeycloakUnreachable("https://kc.example.com/realms/homelab")
    assert e.http_status == 503
    assert e.to_payload() == {
        "error": "oidc_keycloak_unreachable",
        "issuer": "https://kc.example.com/realms/homelab",
    }


def test_oidc_state_missing_payload() -> None:
    e = OidcStateMissing()
    assert e.http_status == 400
    assert e.to_payload() == {"error": "oidc_state_missing"}


def test_oidc_state_mismatch_payload() -> None:
    e = OidcStateMismatch()
    assert e.http_status == 400
    assert e.to_payload() == {"error": "oidc_state_mismatch"}


def test_oidc_invalid_code_payload() -> None:
    e = OidcInvalidCode("invalid_grant")
    assert e.http_status == 400
    assert e.to_payload() == {
        "error": "oidc_invalid_code",
        "reason": "invalid_grant",
    }


def test_oidc_session_missing_payload() -> None:
    e = OidcSessionMissing()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_session_missing"}


def test_oidc_invalid_session_payload() -> None:
    e = OidcInvalidSession()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_invalid_session"}


def test_oidc_session_expired_payload() -> None:
    e = OidcSessionExpired()
    assert e.http_status == 401
    assert e.to_payload() == {"error": "oidc_session_expired"}


def test_oidc_invalid_token_payload() -> None:
    e = OidcInvalidToken("signature_invalid")
    assert e.http_status == 401
    assert e.to_payload() == {
        "error": "oidc_invalid_token",
        "reason": "signature_invalid",
    }


def test_oidc_role_forbidden_payload() -> None:
    e = OidcRoleForbidden(required="rag-admin", has=["rag-viewer"])
    assert e.http_status == 403
    assert e.to_payload() == {
        "error": "oidc_role_forbidden",
        "required": "rag-admin",
        "has": ["rag-viewer"],
    }
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/api/test_oidc_errors.py -v
```

Expected : `ImportError: cannot import name 'OidcNotConfigured' from 'rag.api.errors'`.

- [ ] **Step 3: Ajouter les 10 classes à `api/errors.py`**

Append, juste avant `def register_error_handlers(app: FastAPI)` :

```python
class OidcNotConfigured(AdminError):
    http_status = 503

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "oidc_not_configured",
            "message": "POST /admin/oidc avec la master-key pour configurer Keycloak",
        }


class OidcKeycloakUnreachable(AdminError):
    http_status = 503

    def __init__(self, issuer: str) -> None:
        super().__init__(issuer)
        self.issuer = issuer

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_keycloak_unreachable", "issuer": self.issuer}


class OidcStateMissing(AdminError):
    http_status = 400

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_state_missing"}


class OidcStateMismatch(AdminError):
    http_status = 400

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_state_mismatch"}


class OidcInvalidCode(AdminError):
    http_status = 400

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_code", "reason": self.reason}


class OidcSessionMissing(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_session_missing"}


class OidcInvalidSession(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_session"}


class OidcSessionExpired(AdminError):
    http_status = 401

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_session_expired"}


class OidcInvalidToken(AdminError):
    http_status = 401

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason

    def to_payload(self) -> dict[str, object]:
        return {"error": "oidc_invalid_token", "reason": self.reason}


class OidcRoleForbidden(AdminError):
    http_status = 403

    def __init__(self, *, required: str, has: list[str]) -> None:
        super().__init__(required)
        self.required = required
        self.has = list(has)

    def to_payload(self) -> dict[str, object]:
        return {
            "error": "oidc_role_forbidden",
            "required": self.required,
            "has": self.has,
        }
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/api/test_oidc_errors.py -v
```

Expected : `10 passed`.

- [ ] **Step 5: Run full unit suite (régression)**

```powershell
uv run pytest tests/unit/ --tb=no -q
```

Expected : `≥ 240 passed` (220 baseline M4c + 8 schemas + 10 oidc errors), `0 failed`.

- [ ] **Step 6: Lint/format/mypy**

```powershell
uv run ruff check src/rag/api/errors.py tests/unit/api/
uv run ruff format src/rag/api/errors.py tests/unit/api/
uv run mypy src/rag/api/errors.py
```

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/api/errors.py backend/tests/unit/api/test_oidc_errors.py
git commit -m "feat(M5a): 10 exceptions OIDC (NotConfigured/Unreachable/State/Session/Token/Role)"
```

---

## Task 4: Config — `rag_session_secret` avec fallback master_key

**Files:**
- Modify: `backend/src/rag/config.py`
- Create: `backend/tests/unit/test_config_session_secret.py`

- [ ] **Step 1: Écrire les tests**

```python
# backend/tests/unit/test_config_session_secret.py
from __future__ import annotations

import os
from unittest.mock import patch

import pytest

from rag.config import Settings


_BASE_ENV = {
    "DATABASE_URL": "postgresql://u:p@localhost:5432/rag_config",
    "RAG_POSTGRES_ADMIN_URL": "postgresql://u:p@localhost:5432/postgres",
    "RAG_MASTER_KEY": "x" * 40,  # 40 chars > 32 min
    "RAG_PUBLIC_URL": "http://localhost:8000",
    "HARPOCRATE_API_TOKEN_RAG": "hrpv_test",
    "HARPOCRATE_API_URL_RAG": "https://vault.example.com",
}


def test_session_secret_uses_explicit_value_when_provided() -> None:
    env = {**_BASE_ENV, "RAG_SESSION_SECRET": "y" * 50}
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
        assert s.rag_session_secret.get_secret_value() == "y" * 50


def test_session_secret_falls_back_to_master_key_when_absent() -> None:
    env = {k: v for k, v in _BASE_ENV.items() if k != "RAG_SESSION_SECRET"}
    with patch.dict(os.environ, env, clear=True):
        s = Settings()  # type: ignore[call-arg]
        assert s.rag_session_secret.get_secret_value() == "x" * 40


def test_session_secret_rejected_when_too_short() -> None:
    env = {**_BASE_ENV, "RAG_SESSION_SECRET": "tooshort"}
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="32"):
            Settings()  # type: ignore[call-arg]


def test_master_key_too_short_blocks_fallback() -> None:
    """Si pas de RAG_SESSION_SECRET et que RAG_MASTER_KEY est aussi < 32,
    le fallback échoue avec un message clair."""
    env = {
        **{k: v for k, v in _BASE_ENV.items() if k != "RAG_SESSION_SECRET"},
        "RAG_MASTER_KEY": "shortkey",
    }
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match="32"):
            Settings()  # type: ignore[call-arg]
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/test_config_session_secret.py -v
```

Expected : `AttributeError: 'Settings' object has no attribute 'rag_session_secret'`.

- [ ] **Step 3: Modifier `config.py`**

Dans `backend/src/rag/config.py`, ajouter à la classe `Settings` (après `harpocrate_api_keys`) :

```python
    rag_session_secret: SecretStr = SecretStr("")
```

Et ajouter un nouveau `model_validator(mode="after")` après le `collect_harpocrate_keys` existant :

```python
    @model_validator(mode="after")
    def fill_session_secret_fallback(self) -> "Settings":
        """`RAG_SESSION_SECRET` (32+ chars) signe les cookies `_oidc_session`.

        Fallback dev : si absent, utilise `RAG_MASTER_KEY` (qui doit alors
        être lui-même ≥ 32 chars). En prod, fournir explicitement
        `RAG_SESSION_SECRET=<openssl rand -hex 32>`.
        """
        if not self.rag_session_secret.get_secret_value():
            # Fallback : utilise master_key.
            self.rag_session_secret = self.rag_master_key
        if len(self.rag_session_secret.get_secret_value()) < 32:
            raise ValueError(
                "RAG_SESSION_SECRET must be ≥ 32 chars "
                "(use `openssl rand -hex 32` to generate one)"
            )
        return self
```

**Note** : `model_validator(mode="after")` est appelé après tous les field validators et le `mode="before"` collect_harpocrate_keys. À ce stade `self.rag_master_key` est disponible.

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/test_config_session_secret.py -v
```

Expected : `4 passed`.

- [ ] **Step 5: Run full unit suite**

```powershell
uv run pytest tests/unit/ --tb=no -q
```

Expected : aucun fail. Les tests existants utilisent des fixtures qui posent `RAG_MASTER_KEY` ≥ 32 — vérifier que `mk_test_e2e` (utilisé dans `conftest.py`) fait au moins 32 chars. Si non, la fixture doit être étendue. **Action si fail** : étendre `mk_test_e2e` à `mk_test_e2e_padding_padding_padding_padding_42chars` ou similaire.

- [ ] **Step 6: Si fail, fix la fixture conftest.py**

Si le test full suite signale `ValueError: RAG_SESSION_SECRET must be ≥ 32 chars`, le coupable est probablement `backend/tests/api/conftest.py` ligne ~51 :
```python
os.environ.setdefault("RAG_MASTER_KEY", "mk_test_e2e")
```
qui ne fait que 11 chars. Remplacer par :
```python
os.environ.setdefault("RAG_MASTER_KEY", "mk_test_e2e_" + "x" * 30)
```
(longueur 42).

- [ ] **Step 7: Lint/format/mypy**

```powershell
uv run ruff check src/rag/config.py tests/unit/test_config_session_secret.py
uv run ruff format src/rag/config.py tests/unit/test_config_session_secret.py
uv run mypy src/rag/config.py
```

- [ ] **Step 8: Commit**

```powershell
git add backend/src/rag/config.py backend/tests/unit/test_config_session_secret.py
# Si fixture modifiée :
git add backend/tests/api/conftest.py
git commit -m "feat(M5a): config rag_session_secret (≥32 chars, fallback master_key dev)"
```

---

## Task 5: `OidcService` — squelette + CRUD config

**Files:**
- Create: `backend/src/rag/services/oidc.py`
- Create: `backend/tests/unit/services/test_oidc_config_service.py`

- [ ] **Step 1: Écrire les tests CRUD**

```python
# backend/tests/unit/services/test_oidc_config_service.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.services.oidc import OidcConfig, OidcService


def _fake_pool(returning_rows: list[dict] | None = None) -> MagicMock:
    """Mock asyncpg.Pool avec fetchrow/execute."""
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value=returning_rows[0] if returning_rows else None
    )
    pool.execute = AsyncMock()
    return pool


def _fake_resolver() -> MagicMock:
    r = MagicMock()
    r.resolve_with_retry = MagicMock(return_value="resolved-secret")
    return r


@pytest.mark.asyncio
async def test_get_config_returns_none_when_empty() -> None:
    pool = _fake_pool(returning_rows=None)
    svc = OidcService(
        config_pool=pool,
        secret_resolver=_fake_resolver(),
        public_url="https://rag.example.com",
    )
    assert await svc.get_config() is None


@pytest.mark.asyncio
async def test_get_config_returns_oidc_config_when_present() -> None:
    pool = _fake_pool(returning_rows=[{
        "issuer": "https://kc.example.com/realms/r",
        "client_id": "rag-service",
        "client_secret_ref": "kc_secret",
    }])
    svc = OidcService(
        config_pool=pool,
        secret_resolver=_fake_resolver(),
        public_url="https://rag.example.com",
    )
    cfg = await svc.get_config()
    assert cfg == OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="kc_secret",
    )


@pytest.mark.asyncio
async def test_upsert_config_inserts_first_time() -> None:
    """`upsert_config` doit DELETE puis INSERT (1 row max en table).

    Pattern : on n'autorise qu'une seule config OIDC active à la fois.
    """
    pool = _fake_pool()
    svc = OidcService(
        config_pool=pool,
        secret_resolver=_fake_resolver(),
        public_url="https://rag.example.com",
    )
    cfg = await svc.upsert_config(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="kc_secret",
    )
    assert cfg.client_id == "rag-service"
    # Au moins 2 execute : DELETE + INSERT
    assert pool.execute.await_count >= 2


@pytest.mark.asyncio
async def test_upsert_config_replaces_existing() -> None:
    pool = _fake_pool()
    svc = OidcService(
        config_pool=pool,
        secret_resolver=_fake_resolver(),
        public_url="https://rag.example.com",
    )
    await svc.upsert_config(
        issuer="https://kc-old/realms/r",
        client_id="old",
        client_secret_ref="old_ref",
    )
    pool.execute.reset_mock()
    await svc.upsert_config(
        issuer="https://kc-new/realms/r",
        client_id="new",
        client_secret_ref="new_ref",
    )
    assert pool.execute.await_count >= 2
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/services/test_oidc_config_service.py -v
```

Expected : `ModuleNotFoundError: No module named 'rag.services.oidc'`.

- [ ] **Step 3: Créer `services/oidc.py` (squelette + CRUD)**

```python
# backend/src/rag/services/oidc.py
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import asyncpg
import httpx
import structlog

log = structlog.get_logger(__name__)


class _ResolverProtocol(Protocol):
    def resolve_with_retry(self, ref: str) -> str: ...


@dataclass(frozen=True)
class OidcConfig:
    """Config OIDC stockée en `oidc_config` (1 row max)."""

    issuer: str
    client_id: str
    client_secret_ref: str  # clé logique Harpocrate


class OidcService:
    """Encapsule tout l'état OIDC : config DB, discovery + JWKS cache,
    code exchange, JWT verify, refresh, logout URL.

    Thread-safety : asyncio single-thread → pas de lock requis.
    """

    _DISCOVERY_TTL_SECONDS = 3600

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        secret_resolver: _ResolverProtocol,
        public_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config_pool = config_pool
        self._secret_resolver = secret_resolver
        self._public_url = public_url.rstrip("/")
        self._http_client = http_client  # injection pour tests

    # --- CRUD config ---

    async def get_config(self) -> OidcConfig | None:
        row = await self._config_pool.fetchrow(
            "SELECT issuer, client_id, client_secret_ref FROM oidc_config LIMIT 1"
        )
        if row is None:
            return None
        return OidcConfig(
            issuer=row["issuer"],
            client_id=row["client_id"],
            client_secret_ref=row["client_secret_ref"],
        )

    async def upsert_config(
        self,
        *,
        issuer: str,
        client_id: str,
        client_secret_ref: str,
    ) -> OidcConfig:
        """Remplace toute config existante. Pattern : 1 row max en table.

        DELETE + INSERT plutôt qu'UPSERT car pas de PK naturel — on garantit
        qu'il y a au plus 1 row à tout moment.
        """
        async with self._config_pool.acquire() as conn, conn.transaction():
            await conn.execute("DELETE FROM oidc_config")
            await conn.execute(
                """
                INSERT INTO oidc_config (issuer, client_id, client_secret_ref)
                VALUES ($1, $2, $3)
                """,
                issuer,
                client_id,
                client_secret_ref,
            )
        log.info("oidc.config.upserted", issuer=issuer, client_id=client_id)
        return OidcConfig(
            issuer=issuer,
            client_id=client_id,
            client_secret_ref=client_secret_ref,
        )
```

**Note** : pour le test, `pool.acquire().__aenter__` doit retourner un conn mockable. Adapter les tests si nécessaire pour utiliser un context manager mock comme dans les autres tests M4b/M4c.

Si les tests `upsert` échouent à cause du context manager mock, ajuster le helper `_fake_pool` :

```python
def _fake_pool(returning_rows: list[dict] | None = None) -> MagicMock:
    conn = MagicMock()
    conn.fetchrow = AsyncMock(
        return_value=returning_rows[0] if returning_rows else None
    )
    conn.execute = AsyncMock()
    conn.transaction = MagicMock()
    conn.transaction.return_value.__aenter__ = AsyncMock(return_value=None)
    conn.transaction.return_value.__aexit__ = AsyncMock(return_value=False)
    pool = MagicMock()
    pool.fetchrow = AsyncMock(
        return_value=returning_rows[0] if returning_rows else None
    )
    pool.execute = AsyncMock()
    pool.acquire = MagicMock()
    pool.acquire.return_value.__aenter__ = AsyncMock(return_value=conn)
    pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)
    # Le test inspecte pool.execute.await_count, mais c'est conn.execute qui
    # est appelé. On expose conn.execute via pool pour simplifier l'assertion :
    pool.execute = conn.execute
    return pool
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/services/test_oidc_config_service.py -v
```

Expected : `4 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/oidc.py tests/unit/services/test_oidc_config_service.py
uv run ruff format src/rag/services/oidc.py tests/unit/services/test_oidc_config_service.py
uv run mypy src/rag/services/oidc.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/services/oidc.py backend/tests/unit/services/test_oidc_config_service.py
git commit -m "feat(M5a): OidcService squelette + CRUD oidc_config"
```

---

## Task 6: OidcService — discovery + JWKS cache

**Files:**
- Modify: `backend/src/rag/services/oidc.py`
- Create: `backend/tests/unit/services/test_oidc_discovery.py`

- [ ] **Step 1: Écrire les tests discovery + JWKS**

```python
# backend/tests/unit/services/test_oidc_discovery.py
from __future__ import annotations

import time

import httpx
import pytest

from rag.api.errors import OidcKeycloakUnreachable
from rag.services.oidc import OidcConfig, OidcService


def _make_discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "end_session_endpoint": f"{issuer}/protocol/openid-connect/logout",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }


@pytest.mark.asyncio
async def test_discover_fetches_well_known_and_caches() -> None:
    issuer = "https://kc.example.com/realms/test"
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_make_discovery_payload(issuer))

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,  # pas utilisé dans _discover
        secret_resolver=None,  # idem
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(
        issuer=issuer,
        client_id="rag-service",
        client_secret_ref="x",
    )
    d1 = await svc._discover(cfg)
    d2 = await svc._discover(cfg)  # 2e appel dans la fenêtre TTL
    assert d1.authorization_endpoint == f"{issuer}/protocol/openid-connect/auth"
    assert d1.token_endpoint == f"{issuer}/protocol/openid-connect/token"
    assert d1.end_session_endpoint == f"{issuer}/protocol/openid-connect/logout"
    assert d1.jwks_uri == f"{issuer}/protocol/openid-connect/certs"
    assert call_count == 1  # 2e appel utilise le cache


@pytest.mark.asyncio
async def test_discover_reloads_after_ttl() -> None:
    issuer = "https://kc.example.com/realms/test"
    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_make_discovery_payload(issuer))

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    await svc._discover(cfg)
    # Simule l'expiration du cache en remontant le fetched_at en passé
    for key in list(svc._discovery_cache):
        d = svc._discovery_cache[key]
        svc._discovery_cache[key] = type(d)(
            authorization_endpoint=d.authorization_endpoint,
            token_endpoint=d.token_endpoint,
            end_session_endpoint=d.end_session_endpoint,
            jwks_uri=d.jwks_uri,
            fetched_at=time.monotonic() - 3700,
        )
    await svc._discover(cfg)
    assert call_count == 2  # reload après TTL


@pytest.mark.asyncio
async def test_discover_raises_keycloak_unreachable_on_timeout() -> None:
    issuer = "https://kc.example.com/realms/test"

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("simulated timeout")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    with pytest.raises(OidcKeycloakUnreachable) as exc:
        await svc._discover(cfg)
    assert exc.value.issuer == issuer


@pytest.mark.asyncio
async def test_discover_raises_keycloak_unreachable_on_500() -> None:
    issuer = "https://kc.example.com/realms/test"

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    with pytest.raises(OidcKeycloakUnreachable):
        await svc._discover(cfg)


@pytest.mark.asyncio
async def test_jwks_fetches_and_caches() -> None:
    issuer = "https://kc.example.com/realms/test"
    fake_jwks = {"keys": [{"kty": "RSA", "kid": "test-key", "n": "AQAB", "e": "AQAB"}]}
    discovery_calls = 0
    jwks_calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal discovery_calls, jwks_calls
        if "well-known" in str(request.url):
            discovery_calls += 1
            return httpx.Response(200, json=_make_discovery_payload(issuer))
        jwks_calls += 1
        return httpx.Response(200, json=fake_jwks)

    transport = httpx.MockTransport(handler)
    client = httpx.AsyncClient(transport=transport)

    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="x", client_secret_ref="x")
    d = await svc._discover(cfg)
    await svc._jwks(d)
    await svc._jwks(d)  # cache
    assert jwks_calls == 1
```

- [ ] **Step 2: Run test to verify it fails**

```powershell
uv run pytest tests/unit/services/test_oidc_discovery.py -v
```

Expected : `AttributeError: 'OidcService' object has no attribute '_discover'`.

- [ ] **Step 3: Implémenter discovery + JWKS dans `services/oidc.py`**

Ajouter dans `services/oidc.py`, imports et code :

```python
# Ajouter en haut :
import time
from typing import Any

from authlib.jose import JsonWebKey, KeySet

from rag.api.errors import OidcKeycloakUnreachable


# Ajouter le dataclass après OidcConfig :
@dataclass(frozen=True)
class _DiscoveryDoc:
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str
    jwks_uri: str
    fetched_at: float  # time.monotonic()


# Dans __init__, ajouter les caches :
        self._discovery_cache: dict[str, _DiscoveryDoc] = {}
        self._jwks_cache: dict[str, KeySet] = {}


# Ajouter les méthodes :
    async def _discover(self, config: OidcConfig) -> _DiscoveryDoc:
        """Fetch ${issuer}/.well-known/openid-configuration et cache 1h."""
        key = config.issuer
        cached = self._discovery_cache.get(key)
        if cached is not None and (
            time.monotonic() - cached.fetched_at < self._DISCOVERY_TTL_SECONDS
        ):
            return cached

        url = f"{config.issuer.rstrip('/')}/.well-known/openid-configuration"
        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            try:
                resp = await client.get(url)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise OidcKeycloakUnreachable(config.issuer) from e
            if resp.status_code != 200:
                raise OidcKeycloakUnreachable(config.issuer)
            payload = resp.json()
        finally:
            if owned_client:
                await client.aclose()

        doc = _DiscoveryDoc(
            authorization_endpoint=payload["authorization_endpoint"],
            token_endpoint=payload["token_endpoint"],
            end_session_endpoint=payload["end_session_endpoint"],
            jwks_uri=payload["jwks_uri"],
            fetched_at=time.monotonic(),
        )
        self._discovery_cache[key] = doc
        log.info("oidc.discovery.fetched", issuer=config.issuer)
        return doc

    async def _jwks(self, discovery: _DiscoveryDoc) -> KeySet:
        """Fetch + cache 1h. Pas de TTL séparé : reload happens lors d'un
        verify fail (rotation Keycloak) ou via _discover refresh."""
        cached = self._jwks_cache.get(discovery.jwks_uri)
        if cached is not None:
            return cached

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            try:
                resp = await client.get(discovery.jwks_uri)
            except (httpx.TimeoutException, httpx.NetworkError) as e:
                raise OidcKeycloakUnreachable(discovery.jwks_uri) from e
            if resp.status_code != 200:
                raise OidcKeycloakUnreachable(discovery.jwks_uri)
            payload = resp.json()
        finally:
            if owned_client:
                await client.aclose()

        keyset = JsonWebKey.import_key_set(payload)
        self._jwks_cache[discovery.jwks_uri] = keyset
        log.info("oidc.jwks.fetched", jwks_uri=discovery.jwks_uri)
        return keyset
```

- [ ] **Step 4: Run test to verify it passes**

```powershell
uv run pytest tests/unit/services/test_oidc_discovery.py -v
```

Expected : `5 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/oidc.py tests/unit/services/test_oidc_discovery.py
uv run ruff format src/rag/services/oidc.py tests/unit/services/test_oidc_discovery.py
uv run mypy src/rag/services/oidc.py
```

**Note mypy** : `authlib.jose` n'a probablement pas de stubs. Ajouter dans `pyproject.toml [[tool.mypy.overrides]]` :
```toml
[[tool.mypy.overrides]]
module = ["authlib.*"]
ignore_missing_imports = true
```
(seulement si mypy se plaint.)

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/services/oidc.py backend/tests/unit/services/test_oidc_discovery.py backend/pyproject.toml
git commit -m "feat(M5a): OidcService discovery + JWKS cache (lazy 1h)"
```

---

## Task 7: OidcService — `verify_id_token` + `extract_roles`

**Files:**
- Modify: `backend/src/rag/services/oidc.py`
- Create: `backend/tests/unit/services/test_oidc_verify.py`
- Create: `backend/tests/unit/services/test_oidc_roles.py`

- [ ] **Step 1: Écrire les tests verify**

```python
# backend/tests/unit/services/test_oidc_verify.py
from __future__ import annotations

import time
from typing import Any

import httpx
import pytest
from authlib.jose import JsonWebKey, jwt

from rag.api.errors import OidcInvalidToken
from rag.services.oidc import OidcConfig, OidcService


# Generation d'une paire de clés RSA partagée pour les tests : signe les JWT
# de test localement, expose la public key dans le JWKS mocké.
_RSA_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True)
_KID = "test-key-id"


def _make_signed_jwt(claims: dict[str, Any]) -> str:
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    return jwt.encode(header, claims, _RSA_KEY).decode("ascii")


def _jwks_payload() -> dict:
    pub = _RSA_KEY.as_dict(is_private=False)
    pub["kid"] = _KID
    pub["alg"] = "RS256"
    pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/auth",
        "token_endpoint": f"{issuer}/token",
        "end_session_endpoint": f"{issuer}/logout",
        "jwks_uri": f"{issuer}/jwks",
    }


def _make_service(issuer: str, client_id: str = "rag-service") -> tuple[OidcService, OidcConfig]:
    """Construit un OidcService avec un mock transport qui sert
    discovery + jwks signés avec _RSA_KEY."""
    def handler(request: httpx.Request) -> httpx.Response:
        if "well-known" in str(request.url):
            return httpx.Response(200, json=_discovery_payload(issuer))
        if "jwks" in str(request.url):
            return httpx.Response(200, json=_jwks_payload())
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    # Pour que get_config retourne quelque chose dans les tests qui en ont
    # besoin, on stocke directement le cfg dans le service. Mais ici on le
    # passe en arg à verify_id_token implicitement via le mock — pas nécessaire.
    cfg = OidcConfig(issuer=issuer, client_id=client_id, client_secret_ref="x")
    return svc, cfg


@pytest.mark.asyncio
async def test_verify_id_token_accepts_well_formed_jwt() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": "rag-service",
        "sub": "user-uuid",
        "exp": now + 300,
        "iat": now,
        "nonce": "test-nonce",
    }
    token = _make_signed_jwt(claims)
    decoded = await svc.verify_id_token(token, config=cfg)
    assert decoded["sub"] == "user-uuid"
    assert decoded["nonce"] == "test-nonce"


@pytest.mark.asyncio
async def test_verify_id_token_rejects_bad_signature() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    # Forge un token avec une AUTRE clé RSA
    other_key = JsonWebKey.generate_key("RSA", 2048, is_private=True)
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    claims = {
        "iss": issuer, "aud": "rag-service", "sub": "u",
        "exp": int(time.time()) + 300, "iat": int(time.time()),
    }
    forged = jwt.encode(header, claims, other_key).decode("ascii")
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(forged, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_expired() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer, "aud": "rag-service", "sub": "u",
        "exp": now - 60,  # expired 1 min ago
        "iat": now - 3600,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken, match="expired"):
        await svc.verify_id_token(token, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_issuer() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": "https://attacker.com/realms/evil",
        "aud": "rag-service", "sub": "u",
        "exp": now + 300, "iat": now,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(token, config=cfg)


@pytest.mark.asyncio
async def test_verify_id_token_rejects_wrong_audience() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(issuer)
    now = int(time.time())
    claims = {
        "iss": issuer,
        "aud": "other-service",  # mauvais aud
        "sub": "u", "exp": now + 300, "iat": now,
    }
    token = _make_signed_jwt(claims)
    with pytest.raises(OidcInvalidToken):
        await svc.verify_id_token(token, config=cfg)
```

- [ ] **Step 2: Écrire les tests roles**

```python
# backend/tests/unit/services/test_oidc_roles.py
from __future__ import annotations

from rag.services.oidc import OidcService


def test_extract_roles_present_in_resource_access() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {
        "resource_access": {
            "rag-service": {"roles": ["rag-admin", "rag-viewer"]},
            "other-client": {"roles": ["other-role"]},
        },
    }
    assert svc.extract_roles(claims, "rag-service") == ["rag-admin", "rag-viewer"]


def test_extract_roles_returns_empty_when_resource_access_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    assert svc.extract_roles({}, "rag-service") == []


def test_extract_roles_returns_empty_when_client_id_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {"resource_access": {"other-client": {"roles": ["x"]}}}
    assert svc.extract_roles(claims, "rag-service") == []


def test_extract_roles_returns_empty_when_roles_absent() -> None:
    svc = OidcService(
        config_pool=None,
        secret_resolver=None,
        public_url="https://rag.example.com",
    )
    claims = {"resource_access": {"rag-service": {}}}
    assert svc.extract_roles(claims, "rag-service") == []
```

- [ ] **Step 3: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_oidc_verify.py tests/unit/services/test_oidc_roles.py -v
```

Expected : `AttributeError: 'OidcService' object has no attribute 'verify_id_token'` / `extract_roles`.

- [ ] **Step 4: Implémenter verify + extract_roles**

Append to `services/oidc.py` :

```python
# Imports additionnels (en haut du fichier) :
from authlib.jose import jwt as _jose_jwt
from authlib.jose.errors import (
    BadSignatureError,
    ExpiredTokenError,
    InvalidClaimError,
    JoseError,
)

from rag.api.errors import OidcInvalidToken


# Méthodes à ajouter dans OidcService :
    async def verify_id_token(
        self,
        id_token: str,
        *,
        config: OidcConfig,
    ) -> dict[str, Any]:
        """Vérifie signature (JWKS), iss, aud, exp.

        Raise OidcInvalidToken sur signature/iss/aud invalides.
        Raise OidcInvalidToken("expired") sur exp dépassé.
        """
        discovery = await self._discover(config)
        keyset = await self._jwks(discovery)

        claims_options = {
            "iss": {"essential": True, "value": config.issuer},
            "aud": {"essential": True, "value": config.client_id},
            "exp": {"essential": True},
        }
        try:
            claims = _jose_jwt.decode(
                id_token,
                key=keyset,
                claims_options=claims_options,
            )
            claims.validate()
        except ExpiredTokenError as e:
            raise OidcInvalidToken("expired") from e
        except (BadSignatureError, InvalidClaimError) as e:
            raise OidcInvalidToken(type(e).__name__) from e
        except JoseError as e:
            raise OidcInvalidToken(f"jose_error: {e}") from e

        return dict(claims)

    def extract_roles(self, claims: dict[str, Any], client_id: str) -> list[str]:
        """Extract `claims.resource_access.<client_id>.roles` ou []."""
        resource_access = claims.get("resource_access") or {}
        client_section = resource_access.get(client_id) or {}
        roles = client_section.get("roles") or []
        return list(roles)
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_oidc_verify.py tests/unit/services/test_oidc_roles.py -v
```

Expected : `5 passed` (verify) + `4 passed` (roles).

- [ ] **Step 6: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/oidc.py tests/unit/services/test_oidc_verify.py tests/unit/services/test_oidc_roles.py
uv run ruff format src/rag/services/oidc.py tests/unit/services/test_oidc_verify.py tests/unit/services/test_oidc_roles.py
uv run mypy src/rag/services/oidc.py
```

- [ ] **Step 7: Commit**

```powershell
git add backend/src/rag/services/oidc.py backend/tests/unit/services/test_oidc_verify.py backend/tests/unit/services/test_oidc_roles.py
git commit -m "feat(M5a): OidcService verify_id_token + extract_roles"
```

---

## Task 8: OidcService — `build_authorize_url` + `build_logout_url`

**Files:**
- Modify: `backend/src/rag/services/oidc.py`
- Create: `backend/tests/unit/services/test_oidc_authorize_url.py`

- [ ] **Step 1: Écrire les tests**

```python
# backend/tests/unit/services/test_oidc_authorize_url.py
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from rag.services.oidc import OidcConfig, OidcService


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/protocol/openid-connect/auth",
        "token_endpoint": f"{issuer}/protocol/openid-connect/token",
        "end_session_endpoint": f"{issuer}/protocol/openid-connect/logout",
        "jwks_uri": f"{issuer}/protocol/openid-connect/certs",
    }


def _make_service_with_config(issuer: str) -> OidcService:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_discovery_payload(issuer))

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    pool = MagicMock()
    pool.fetchrow = AsyncMock(return_value={
        "issuer": issuer,
        "client_id": "rag-service",
        "client_secret_ref": "kc_secret",
    })
    svc = OidcService(
        config_pool=pool,
        secret_resolver=None,
        public_url="https://rag.example.com",
        http_client=client,
    )
    return svc


@pytest.mark.asyncio
async def test_build_authorize_url_includes_required_params() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    url, state, nonce = await svc.build_authorize_url()
    parsed = urlparse(url)
    params = parse_qs(parsed.query)

    assert parsed.netloc == "kc.example.com"
    assert parsed.path == "/realms/test/protocol/openid-connect/auth"
    assert params["client_id"] == ["rag-service"]
    assert params["redirect_uri"] == ["https://rag.example.com/auth/callback"]
    assert params["response_type"] == ["code"]
    assert "openid" in params["scope"][0]
    assert params["state"] == [state]
    assert params["nonce"] == [nonce]
    # state et nonce sont des strings aléatoires non vides
    assert len(state) >= 16
    assert len(nonce) >= 16


@pytest.mark.asyncio
async def test_build_authorize_url_state_and_nonce_unique() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    _, s1, n1 = await svc.build_authorize_url()
    _, s2, n2 = await svc.build_authorize_url()
    assert s1 != s2
    assert n1 != n2


@pytest.mark.asyncio
async def test_build_logout_url_includes_id_token_hint_and_redirect() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc = _make_service_with_config(issuer)
    cfg = await svc.get_config()
    assert cfg is not None
    url = await svc.build_logout_url(id_token="dummy.jwt.value", config=cfg)
    parsed = urlparse(url)
    params = parse_qs(parsed.query)
    assert parsed.path == "/realms/test/protocol/openid-connect/logout"
    assert params["id_token_hint"] == ["dummy.jwt.value"]
    assert params["post_logout_redirect_uri"] == ["https://rag.example.com/"]
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_oidc_authorize_url.py -v
```

Expected : `AttributeError: 'OidcService' object has no attribute 'build_authorize_url'`.

- [ ] **Step 3: Implémenter build_authorize_url + build_logout_url**

Append to `services/oidc.py` :

```python
# Imports additionnels (en haut) :
import secrets
from urllib.parse import urlencode

from rag.api.errors import OidcNotConfigured


# Méthodes à ajouter dans OidcService :
    async def build_authorize_url(self) -> tuple[str, str, str]:
        """Construit l'URL d'authorize Keycloak avec state + nonce aléatoires.

        Returns (url, state, nonce). Le caller stocke (state, nonce) dans
        un cookie éphémère pour validation au callback.

        Raise OidcNotConfigured si aucune config OIDC en DB.
        """
        cfg = await self.get_config()
        if cfg is None:
            raise OidcNotConfigured()
        discovery = await self._discover(cfg)

        state = secrets.token_urlsafe(32)
        nonce = secrets.token_urlsafe(32)
        params = {
            "client_id": cfg.client_id,
            "redirect_uri": f"{self._public_url}/auth/callback",
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "nonce": nonce,
        }
        url = f"{discovery.authorization_endpoint}?{urlencode(params)}"
        return url, state, nonce

    async def build_logout_url(self, *, id_token: str, config: OidcConfig) -> str:
        """Construit l'URL de logout Keycloak avec id_token_hint."""
        discovery = await self._discover(config)
        params = {
            "id_token_hint": id_token,
            "post_logout_redirect_uri": f"{self._public_url}/",
        }
        return f"{discovery.end_session_endpoint}?{urlencode(params)}"
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_oidc_authorize_url.py -v
```

Expected : `3 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/oidc.py tests/unit/services/test_oidc_authorize_url.py
uv run ruff format src/rag/services/oidc.py tests/unit/services/test_oidc_authorize_url.py
uv run mypy src/rag/services/oidc.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/services/oidc.py backend/tests/unit/services/test_oidc_authorize_url.py
git commit -m "feat(M5a): OidcService build_authorize_url + build_logout_url"
```

---

## Task 9: OidcService — `exchange_code` + `refresh`

**Files:**
- Modify: `backend/src/rag/services/oidc.py`
- Create: `backend/tests/unit/services/test_oidc_exchange.py`

- [ ] **Step 1: Écrire les tests exchange + refresh**

```python
# backend/tests/unit/services/test_oidc_exchange.py
from __future__ import annotations

import json
import time
from typing import Any

import httpx
import pytest
from authlib.jose import JsonWebKey, jwt

from rag.api.errors import OidcInvalidCode, OidcInvalidToken, OidcSessionExpired
from rag.services.oidc import OidcConfig, OidcService


_RSA_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True)
_KID = "test-key"


def _signed(claims: dict[str, Any]) -> str:
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    return jwt.encode(header, claims, _RSA_KEY).decode("ascii")


def _jwks_payload() -> dict:
    pub = _RSA_KEY.as_dict(is_private=False)
    pub["kid"] = _KID
    pub["alg"] = "RS256"
    pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery_payload(issuer: str) -> dict:
    return {
        "issuer": issuer,
        "authorization_endpoint": f"{issuer}/auth",
        "token_endpoint": f"{issuer}/token",
        "end_session_endpoint": f"{issuer}/logout",
        "jwks_uri": f"{issuer}/jwks",
    }


class _FakeResolver:
    def resolve_with_retry(self, _ref: str) -> str:
        return "resolved-client-secret"


def _make_service(
    issuer: str,
    *,
    token_response: dict | None = None,
    token_status: int = 200,
    token_error_payload: dict | None = None,
) -> tuple[OidcService, OidcConfig]:
    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery_payload(issuer))
        if "jwks" in url:
            return httpx.Response(200, json=_jwks_payload())
        if url.endswith("/token"):
            if token_status != 200:
                return httpx.Response(token_status, json=token_error_payload or {})
            return httpx.Response(200, json=token_response or {})
        return httpx.Response(404)

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    svc = OidcService(
        config_pool=None,
        secret_resolver=_FakeResolver(),
        public_url="https://rag.example.com",
        http_client=client,
    )
    cfg = OidcConfig(issuer=issuer, client_id="rag-service", client_secret_ref="kc_secret")
    return svc, cfg


@pytest.mark.asyncio
async def test_exchange_code_happy_path() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    id_token = _signed({
        "iss": issuer, "aud": "rag-service", "sub": "u",
        "exp": now + 300, "iat": now, "nonce": "expected-nonce",
    })
    svc, cfg = _make_service(issuer, token_response={
        "id_token": id_token,
        "access_token": "at-xyz",
        "refresh_token": "rt-xyz",
        "expires_in": 300,
        "token_type": "Bearer",
    })
    tokens = await svc.exchange_code(
        code="auth-code-xyz",
        expected_nonce="expected-nonce",
        config=cfg,
    )
    assert tokens.id_token == id_token
    assert tokens.access_token == "at-xyz"
    assert tokens.refresh_token == "rt-xyz"
    assert tokens.expires_at > now


@pytest.mark.asyncio
async def test_exchange_code_rejects_nonce_mismatch() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    id_token = _signed({
        "iss": issuer, "aud": "rag-service", "sub": "u",
        "exp": now + 300, "iat": now, "nonce": "actual-nonce",
    })
    svc, cfg = _make_service(issuer, token_response={
        "id_token": id_token,
        "access_token": "at",
        "refresh_token": "rt",
        "expires_in": 300,
    })
    with pytest.raises(OidcInvalidToken, match="nonce"):
        await svc.exchange_code(
            code="x",
            expected_nonce="other-nonce",
            config=cfg,
        )


@pytest.mark.asyncio
async def test_exchange_code_rejects_400_keycloak_error() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(
        issuer,
        token_status=400,
        token_error_payload={"error": "invalid_grant"},
    )
    with pytest.raises(OidcInvalidCode) as exc:
        await svc.exchange_code(code="x", expected_nonce="n", config=cfg)
    assert exc.value.reason == "invalid_grant"


@pytest.mark.asyncio
async def test_refresh_happy_path() -> None:
    issuer = "https://kc.example.com/realms/test"
    now = int(time.time())
    new_id_token = _signed({
        "iss": issuer, "aud": "rag-service", "sub": "u",
        "exp": now + 300, "iat": now,
    })
    svc, cfg = _make_service(issuer, token_response={
        "id_token": new_id_token,
        "access_token": "new-at",
        "refresh_token": "new-rt",
        "expires_in": 300,
    })
    tokens = await svc.refresh(refresh_token="old-rt", config=cfg)
    assert tokens.id_token == new_id_token
    assert tokens.refresh_token == "new-rt"


@pytest.mark.asyncio
async def test_refresh_rejected_raises_session_expired() -> None:
    issuer = "https://kc.example.com/realms/test"
    svc, cfg = _make_service(
        issuer,
        token_status=400,
        token_error_payload={"error": "invalid_grant"},
    )
    with pytest.raises(OidcSessionExpired):
        await svc.refresh(refresh_token="stale-rt", config=cfg)
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/services/test_oidc_exchange.py -v
```

Expected : `AttributeError: 'OidcService' object has no attribute 'exchange_code'`.

- [ ] **Step 3: Implémenter exchange_code + refresh + _TokenPair**

Append to `services/oidc.py` :

```python
# Import additionnel :
from rag.api.errors import OidcInvalidCode, OidcSessionExpired


# Dataclass après _DiscoveryDoc :
@dataclass(frozen=True)
class _TokenPair:
    id_token: str
    access_token: str
    refresh_token: str
    expires_at: int  # epoch seconds


# Méthodes dans OidcService :
    async def exchange_code(
        self,
        *,
        code: str,
        expected_nonce: str,
        config: OidcConfig,
    ) -> _TokenPair:
        """POST token_endpoint avec grant_type=authorization_code.
        Vérifie nonce dans id_token décodé.

        Raise OidcInvalidCode si Keycloak rejette le code.
        Raise OidcInvalidToken si nonce ne match pas.
        """
        return await self._token_request(
            config=config,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": f"{self._public_url}/auth/callback",
            },
            expected_nonce=expected_nonce,
        )

    async def refresh(
        self,
        *,
        refresh_token: str,
        config: OidcConfig,
    ) -> _TokenPair:
        """POST token_endpoint avec grant_type=refresh_token.

        Raise OidcSessionExpired si Keycloak rejette le refresh_token.
        """
        try:
            return await self._token_request(
                config=config,
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                expected_nonce=None,
            )
        except OidcInvalidCode as e:
            raise OidcSessionExpired() from e

    async def _token_request(
        self,
        *,
        config: OidcConfig,
        data: dict[str, str],
        expected_nonce: str | None,
    ) -> _TokenPair:
        discovery = await self._discover(config)
        client_secret = self._secret_resolver.resolve_with_retry(
            f"${{vault://rag:{config.client_secret_ref}}}"
        )
        payload = {
            **data,
            "client_id": config.client_id,
            "client_secret": client_secret,
        }

        client = self._http_client or httpx.AsyncClient(timeout=10.0)
        owned_client = self._http_client is None
        try:
            resp = await client.post(discovery.token_endpoint, data=payload)
        finally:
            if owned_client:
                await client.aclose()

        if resp.status_code != 200:
            try:
                body = resp.json()
                reason = body.get("error", f"http_{resp.status_code}")
            except Exception:
                reason = f"http_{resp.status_code}"
            raise OidcInvalidCode(reason)

        body = resp.json()
        id_token = body["id_token"]

        # Verify nonce si attendu (callback) — pour refresh, nonce absent.
        if expected_nonce is not None:
            claims = await self.verify_id_token(id_token, config=config)
            if claims.get("nonce") != expected_nonce:
                raise OidcInvalidToken("nonce_mismatch")

        now = int(time.time())
        return _TokenPair(
            id_token=id_token,
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token", ""),
            expires_at=now + int(body.get("expires_in", 300)),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/services/test_oidc_exchange.py -v
```

Expected : `5 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/services/oidc.py tests/unit/services/test_oidc_exchange.py
uv run ruff format src/rag/services/oidc.py tests/unit/services/test_oidc_exchange.py
uv run mypy src/rag/services/oidc.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/services/oidc.py backend/tests/unit/services/test_oidc_exchange.py
git commit -m "feat(M5a): OidcService exchange_code + refresh + _TokenPair"
```

---

## Task 10: Dependency `require_oidc_role`

**Files:**
- Create: `backend/src/rag/auth/oidc_dependency.py`
- Create: `backend/tests/unit/auth/test_oidc_dependency.py`

- [ ] **Step 1: Écrire les tests de la dependency**

```python
# backend/tests/unit/auth/test_oidc_dependency.py
from __future__ import annotations

import time
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from rag.api.errors import (
    OidcInvalidToken,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
)
from rag.auth.oidc_dependency import _role_grants, require_oidc_role
from rag.services.oidc import OidcConfig


def test_role_grants_exact_match() -> None:
    assert _role_grants("rag-admin", user_roles=["rag-admin"]) is True
    assert _role_grants("rag-viewer", user_roles=["rag-viewer"]) is True


def test_role_grants_admin_includes_viewer() -> None:
    """Hierarchy : rag-admin a tous les droits du rag-viewer."""
    assert _role_grants("rag-viewer", user_roles=["rag-admin"]) is True


def test_role_grants_viewer_does_not_include_admin() -> None:
    assert _role_grants("rag-admin", user_roles=["rag-viewer"]) is False


def test_role_grants_returns_false_when_no_role() -> None:
    assert _role_grants("rag-viewer", user_roles=[]) is False


def _fake_request(
    *,
    session: dict[str, Any] | None,
    oidc_service: MagicMock,
) -> SimpleNamespace:
    return SimpleNamespace(
        session=session if session is not None else {},
        app=SimpleNamespace(state=SimpleNamespace(oidc=oidc_service)),
    )


@pytest.mark.asyncio
async def test_dependency_raises_session_missing_when_no_session() -> None:
    oidc = MagicMock()
    req = _fake_request(session={}, oidc_service=oidc)
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcSessionMissing):
        await dep(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_raises_session_expired_when_token_expired() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(side_effect=OidcInvalidToken("expired"))
    oidc.get_config = AsyncMock(return_value=OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="x",
    ))
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x.y.z", "refresh_token": "rt", "exp": int(time.time())}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcSessionExpired):
        await dep(req)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_dependency_returns_user_context_when_role_matches() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={
        "sub": "user-uuid",
        "email": "user@example.com",
        "name": "Test User",
        "resource_access": {"rag-service": {"roles": ["rag-admin"]}},
    })
    oidc.get_config = AsyncMock(return_value=OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="x",
    ))
    oidc.extract_roles = MagicMock(return_value=["rag-admin"])
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x.y.z", "refresh_token": "rt", "exp": int(time.time()) + 300}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-admin")
    ctx = await dep(req)  # type: ignore[arg-type]
    assert ctx.sub == "user-uuid"
    assert ctx.email == "user@example.com"
    assert ctx.roles == ["rag-admin"]


@pytest.mark.asyncio
async def test_dependency_admin_grants_viewer_endpoint() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u", "email": None, "name": None})
    oidc.get_config = AsyncMock(return_value=OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="x",
    ))
    oidc.extract_roles = MagicMock(return_value=["rag-admin"])
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": int(time.time()) + 300}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    ctx = await dep(req)  # type: ignore[arg-type]
    assert "rag-admin" in ctx.roles


@pytest.mark.asyncio
async def test_dependency_viewer_cannot_access_admin_endpoint() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u", "email": None, "name": None})
    oidc.get_config = AsyncMock(return_value=OidcConfig(
        issuer="https://kc.example.com/realms/r",
        client_id="rag-service",
        client_secret_ref="x",
    ))
    oidc.extract_roles = MagicMock(return_value=["rag-viewer"])
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": int(time.time()) + 300}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-admin")
    with pytest.raises(OidcRoleForbidden) as exc:
        await dep(req)  # type: ignore[arg-type]
    assert exc.value.required == "rag-admin"
    assert "rag-viewer" in exc.value.has


@pytest.mark.asyncio
async def test_dependency_raises_not_configured_when_oidc_absent() -> None:
    oidc = MagicMock()
    oidc.verify_id_token = AsyncMock(return_value={"sub": "u"})
    oidc.get_config = AsyncMock(return_value=None)
    req = _fake_request(
        session={"_oidc_session": {"id_token": "x", "refresh_token": "rt", "exp": int(time.time()) + 300}},
        oidc_service=oidc,
    )
    dep = require_oidc_role("rag-viewer")
    with pytest.raises(OidcNotConfigured):
        await dep(req)  # type: ignore[arg-type]
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
uv run pytest tests/unit/auth/test_oidc_dependency.py -v
```

Expected : `ModuleNotFoundError: No module named 'rag.auth.oidc_dependency'`.

- [ ] **Step 3: Implémenter `auth/oidc_dependency.py`**

```python
# backend/src/rag/auth/oidc_dependency.py
from __future__ import annotations

from collections.abc import Awaitable, Callable

from fastapi import Request

from rag.api.errors import (
    OidcInvalidToken,
    OidcNotConfigured,
    OidcRoleForbidden,
    OidcSessionExpired,
    OidcSessionMissing,
)
from rag.schemas.oidc import OidcUserContext


_SESSION_KEY = "_oidc_session"


def _role_grants(required: str, *, user_roles: list[str]) -> bool:
    """Hierarchy : `rag-admin` grants `rag-viewer`."""
    if required in user_roles:
        return True
    if required == "rag-viewer" and "rag-admin" in user_roles:
        return True
    return False


def require_oidc_role(
    role: str,
) -> Callable[[Request], Awaitable[OidcUserContext]]:
    """Factory de dependency FastAPI.

    Usage : `auth: OidcUserContext = Depends(require_oidc_role("rag-admin"))`.

    Raises (mappés en codes HTTP via le handler global) :
    - 401 OidcSessionMissing si cookie `_oidc_session` absent.
    - 401 OidcSessionExpired si id_token expiré (frontend doit POST /auth/refresh).
    - 401 OidcInvalidToken si signature/iss/aud invalides.
    - 403 OidcRoleForbidden si role insuffisant.
    - 503 OidcNotConfigured si oidc_config absent en DB.
    """

    async def _dep(request: Request) -> OidcUserContext:
        session = request.session.get(_SESSION_KEY)
        if not session:
            raise OidcSessionMissing()

        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        id_token = session.get("id_token")
        if not id_token:
            raise OidcSessionMissing()

        try:
            claims = await oidc.verify_id_token(id_token, config=cfg)
        except OidcInvalidToken as e:
            if e.reason == "expired":
                raise OidcSessionExpired() from e
            raise

        user_roles = oidc.extract_roles(claims, cfg.client_id)
        if not _role_grants(role, user_roles=user_roles):
            raise OidcRoleForbidden(required=role, has=user_roles)

        return OidcUserContext(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            roles=user_roles,
        )

    return _dep
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
uv run pytest tests/unit/auth/test_oidc_dependency.py -v
```

Expected : `10 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/auth/oidc_dependency.py tests/unit/auth/test_oidc_dependency.py
uv run ruff format src/rag/auth/oidc_dependency.py tests/unit/auth/test_oidc_dependency.py
uv run mypy src/rag/auth/oidc_dependency.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/auth/oidc_dependency.py backend/tests/unit/auth/test_oidc_dependency.py
git commit -m "feat(M5a): require_oidc_role dependency + hierarchy admin>viewer"
```

---

## Task 11: Router `/admin/oidc` (CRUD master-key)

**Files:**
- Create: `backend/src/rag/api/admin_oidc.py`
- Create: `backend/tests/api/test_admin_oidc.py`

- [ ] **Step 1: Créer le router**

```python
# backend/src/rag/api/admin_oidc.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from rag.api.errors import OidcNotConfigured
from rag.auth.bearer import require_master_key
from rag.schemas.oidc import OidcConfigCreate, OidcConfigRead


def build_admin_oidc_router() -> APIRouter:
    """Router master-key : CRUD config OIDC (singleton)."""
    router = APIRouter(
        tags=["admin"],
        dependencies=[Depends(require_master_key)],
    )

    @router.post("/admin/oidc", status_code=status.HTTP_201_CREATED)
    async def post_oidc_config(
        payload: OidcConfigCreate, request: Request
    ) -> OidcConfigRead:
        cfg = await request.app.state.oidc.upsert_config(
            issuer=str(payload.issuer),
            client_id=payload.client_id,
            client_secret_ref=payload.client_secret_ref,
        )
        return OidcConfigRead(
            issuer=cfg.issuer,
            client_id=cfg.client_id,
            client_secret_ref=cfg.client_secret_ref,
        )

    @router.get("/admin/oidc")
    async def get_oidc_config(request: Request) -> OidcConfigRead:
        cfg = await request.app.state.oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()
        return OidcConfigRead(
            issuer=cfg.issuer,
            client_id=cfg.client_id,
            client_secret_ref=cfg.client_secret_ref,
        )

    return router
```

- [ ] **Step 2: Écrire les tests integration**

```python
# backend/tests/api/test_admin_oidc.py
from __future__ import annotations

from fastapi.testclient import TestClient


def test_post_oidc_creates_config(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["client_id"] == "rag-service"


def test_get_oidc_returns_503_when_not_configured(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_post_then_get_returns_same_config(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "ref1",
        },
    )
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    assert r.status_code == 200
    assert r.json()["client_secret_ref"] == "ref1"


def test_post_replaces_existing_config(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc-old/realms/r",
            "client_id": "old",
            "client_secret_ref": "old_ref",
        },
    )
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc-new/realms/r",
            "client_id": "new",
            "client_secret_ref": "new_ref",
        },
    )
    r = admin_client.get("/admin/oidc", headers=admin_headers)
    body = r.json()
    assert body["client_id"] == "new"
    assert body["client_secret_ref"] == "new_ref"


def test_post_without_master_key_returns_401(
    admin_client: TestClient,
) -> None:
    r = admin_client.post(
        "/admin/oidc",
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 401


def test_post_422_for_invalid_issuer(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    r = admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "not-a-url",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    assert r.status_code == 422
```

- [ ] **Step 3: Wiring partiel main.py pour permettre les tests**

(Sera plus complet en T13 ; juste assez pour les tests admin_oidc.)

Edit `backend/src/rag/main.py`. Ajouter imports en haut :

```python
from rag.api.admin_oidc import build_admin_oidc_router
from rag.services.oidc import OidcService
```

Dans `build_app` lifespan, après `app.state.resolver = resolver_factory(settings)` :

```python
        app.state.oidc = OidcService(
            config_pool=registry.config_pool,
            secret_resolver=app.state.resolver,
            public_url=str(settings.rag_public_url).rstrip("/"),
        )
```

Après `app.include_router(build_workspace_router())` :

```python
    app.include_router(build_admin_oidc_router())
```

- [ ] **Step 4: Run tests**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_admin_oidc.py -v
```

Expected : `6 passed`.

- [ ] **Step 5: Lint/format/mypy**

```powershell
uv run ruff check src/rag/api/admin_oidc.py src/rag/main.py tests/api/test_admin_oidc.py
uv run ruff format src/rag/api/admin_oidc.py src/rag/main.py tests/api/test_admin_oidc.py
uv run mypy src/rag/api/admin_oidc.py src/rag/main.py
```

- [ ] **Step 6: Commit**

```powershell
git add backend/src/rag/api/admin_oidc.py backend/src/rag/main.py backend/tests/api/test_admin_oidc.py
git commit -m "feat(M5a): router /admin/oidc CRUD (master-key) + wiring OidcService"
```

---

## Task 12: Router `/auth/*` + `/me`

**Files:**
- Create: `backend/src/rag/api/auth.py`
- Modify: `backend/src/rag/main.py` (add SessionMiddleware + include router)

- [ ] **Step 1: Créer le router**

```python
# backend/src/rag/api/auth.py
from __future__ import annotations

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import RedirectResponse

from rag.api.errors import (
    OidcNotConfigured,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)
from rag.auth.oidc_dependency import require_oidc_role
from rag.schemas.oidc import MeResponse, OidcUserContext


_SESSION_KEY = "_oidc_session"
_STATE_KEY = "_oidc_state"


def _safe_next(raw: str | None) -> str:
    """Anti open-redirect : accept only path relatif `/...` qui ne commence
    pas par `//` (qui pourrait être protocol-relative)."""
    if not raw or not raw.startswith("/") or raw.startswith("//"):
        return "/"
    return raw


def build_auth_router() -> APIRouter:
    """Router IHM (cookies session signés)."""
    router = APIRouter(tags=["auth"])

    @router.get("/auth/login")
    async def login(request: Request, next: str = "/") -> RedirectResponse:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        url, state, nonce = await oidc.build_authorize_url()
        # Stocke (state, nonce, next) dans session signée (5 min effective via
        # nettoyage côté callback — pas de TTL natif Starlette session).
        request.session[_STATE_KEY] = {
            "state": state,
            "nonce": nonce,
            "next": _safe_next(next),
        }
        return RedirectResponse(url=url, status_code=302)

    @router.get("/auth/callback")
    async def callback(
        request: Request,
        code: str | None = None,
        state: str | None = None,
    ) -> RedirectResponse:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        state_payload = request.session.get(_STATE_KEY)
        if not state_payload or not isinstance(state_payload, dict):
            raise OidcStateMissing()
        if not code or not state or state != state_payload.get("state"):
            raise OidcStateMismatch()

        tokens = await oidc.exchange_code(
            code=code,
            expected_nonce=state_payload["nonce"],
            config=cfg,
        )
        # Set session cookie (signée par SessionMiddleware).
        request.session[_SESSION_KEY] = {
            "id_token": tokens.id_token,
            "refresh_token": tokens.refresh_token,
            "exp": tokens.expires_at,
        }
        # Clear state payload
        request.session.pop(_STATE_KEY, None)

        next_path = _safe_next(state_payload.get("next"))
        return RedirectResponse(url=next_path, status_code=302)

    @router.post("/auth/refresh", status_code=status.HTTP_200_OK)
    async def refresh(request: Request) -> dict[str, bool]:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        session = request.session.get(_SESSION_KEY)
        if not session or not session.get("refresh_token"):
            raise OidcSessionMissing()

        try:
            tokens = await oidc.refresh(
                refresh_token=session["refresh_token"],
                config=cfg,
            )
        except OidcSessionExpired:
            request.session.pop(_SESSION_KEY, None)
            raise

        request.session[_SESSION_KEY] = {
            "id_token": tokens.id_token,
            "refresh_token": tokens.refresh_token or session["refresh_token"],
            "exp": tokens.expires_at,
        }
        return {"ok": True}

    @router.post("/auth/logout")
    async def logout(request: Request) -> Response:
        oidc = request.app.state.oidc
        cfg = await oidc.get_config()
        session = request.session.get(_SESSION_KEY)
        id_token = session.get("id_token") if session else None

        # Clear session locally.
        request.session.pop(_SESSION_KEY, None)
        request.session.pop(_STATE_KEY, None)

        if cfg is not None and id_token:
            logout_url = await oidc.build_logout_url(id_token=id_token, config=cfg)
        else:
            logout_url = f"{str(request.app.state.public_url).rstrip('/')}/"
        return RedirectResponse(url=logout_url, status_code=302)

    @router.get("/me", response_model=MeResponse)
    async def me(
        user: OidcUserContext = Depends(require_oidc_role("rag-viewer")),  # noqa: B008
    ) -> MeResponse:
        return MeResponse(
            sub=user.sub,
            email=user.email,
            name=user.name,
            roles=user.roles,
        )

    return router
```

- [ ] **Step 2: Modifier `main.py` — ajouter SessionMiddleware + include auth router**

Dans `backend/src/rag/main.py` :

a) Imports :
```python
from starlette.middleware.sessions import SessionMiddleware

from rag.api.auth import build_auth_router
```

b) Dans `build_app`, après l'instanciation de l'app `FastAPI(...)` et AVANT les `include_router` :

```python
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.rag_session_secret.get_secret_value(),
        same_site="lax",
        https_only=(settings.environment != "dev"),
    )
```

c) Dans le lifespan, après `app.state.oidc = OidcService(...)` :

```python
        app.state.public_url = str(settings.rag_public_url).rstrip("/")
```

d) Après le `include_router(build_admin_oidc_router())` :

```python
    app.include_router(build_auth_router())
```

- [ ] **Step 3: Smoke test — pas de régression sur les routers existants**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_main.py tests/api/test_admin_wireup.py tests/api/test_admin_oidc.py -v
```

Expected : tous passent, pas de régression.

- [ ] **Step 4: Lint/format/mypy**

```powershell
uv run ruff check src/rag/api/auth.py src/rag/main.py
uv run ruff format src/rag/api/auth.py src/rag/main.py
uv run mypy src/rag/api/auth.py src/rag/main.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/src/rag/api/auth.py backend/src/rag/main.py
git commit -m "feat(M5a): router /auth (login/callback/refresh/logout/me) + SessionMiddleware"
```

---

## Task 13: Tests integration — auth flow (Keycloak mocké)

**Files:**
- Create: `backend/tests/api/test_auth_flow.py`

- [ ] **Step 1: Écrire les tests E2E avec Keycloak mocké**

```python
# backend/tests/api/test_auth_flow.py
from __future__ import annotations

import time
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
from authlib.jose import JsonWebKey, jwt
from fastapi.testclient import TestClient


_RSA_KEY = JsonWebKey.generate_key("RSA", 2048, is_private=True)
_KID = "test-kid"
_ISSUER = "https://kc.example.com/realms/test"
_CLIENT_ID = "rag-service"


def _signed(claims: dict[str, Any]) -> str:
    header = {"alg": "RS256", "kid": _KID, "typ": "JWT"}
    return jwt.encode(header, claims, _RSA_KEY).decode("ascii")


def _jwks() -> dict:
    pub = _RSA_KEY.as_dict(is_private=False)
    pub["kid"] = _KID
    pub["alg"] = "RS256"
    pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery() -> dict:
    return {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/protocol/openid-connect/auth",
        "token_endpoint": f"{_ISSUER}/protocol/openid-connect/token",
        "end_session_endpoint": f"{_ISSUER}/protocol/openid-connect/logout",
        "jwks_uri": f"{_ISSUER}/protocol/openid-connect/certs",
    }


def _install_keycloak_mock(client: TestClient, *, roles: list[str] | None = None) -> None:
    """Remplace le http_client de l'OidcService par un mock qui simule
    discovery, JWKS, token_endpoint. Le token_endpoint retourne un
    id_token signé avec _RSA_KEY contenant les roles fournis.

    Pour récupérer le nonce demandé, le mock le lit depuis le body POST
    (le caller stocke `_last_request_nonce` côté test fixture).
    """
    # nonce sera injecté par le test via attribut sur la closure.
    state: dict[str, str] = {"last_nonce": ""}

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery())
        if "/certs" in url:
            return httpx.Response(200, json=_jwks())
        if url.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": _ISSUER,
                "aud": _CLIENT_ID,
                "sub": "user-uuid-42",
                "email": "test@example.com",
                "name": "Test User",
                "exp": now + 300,
                "iat": now,
                "nonce": state["last_nonce"],
                "resource_access": {
                    _CLIENT_ID: {"roles": roles or ["rag-viewer"]},
                },
            }
            return httpx.Response(200, json={
                "id_token": _signed(claims),
                "access_token": "at-test",
                "refresh_token": "rt-test",
                "expires_in": 300,
                "token_type": "Bearer",
            })
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)
    new_client = httpx.AsyncClient(transport=transport)
    client.app.state.oidc._http_client = new_client  # type: ignore[attr-defined]
    # Expose le state pour que les tests le complètent au login
    client.app.state._kc_mock_state = state  # type: ignore[attr-defined]


def _seed_oidc_config(client: TestClient, admin_headers: dict[str, str]) -> None:
    r = client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": _ISSUER,
            "client_id": _CLIENT_ID,
            "client_secret_ref": "kc_test_secret",
        },
    )
    assert r.status_code == 201, r.text


def _stub_secret_resolver(client: TestClient) -> None:
    """Le stub resolver de conftest accepte déjà des refs connues ;
    on ajoute kc_test_secret."""
    client.app.state.resolver.known.add("kc_test_secret")  # type: ignore[attr-defined]


def test_auth_login_redirects_to_keycloak_with_state_and_nonce(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    r = admin_client.get("/auth/login?next=/ui/workspaces", follow_redirects=False)
    assert r.status_code == 302
    location = r.headers["location"]
    parsed = urlparse(location)
    params = parse_qs(parsed.query)
    assert parsed.netloc == "kc.example.com"
    assert params["client_id"] == [_CLIENT_ID]
    assert "state" in params
    assert "nonce" in params


def test_auth_callback_sets_session_cookie_and_redirects_next(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # 1. /auth/login pour capturer state + nonce (et set state cookie)
    login_r = admin_client.get("/auth/login?next=/ui/x", follow_redirects=False)
    auth_url = login_r.headers["location"]
    params = parse_qs(urlparse(auth_url).query)
    state = params["state"][0]
    nonce = params["nonce"][0]
    # Le mock Keycloak va recevoir le code et retourner un id_token avec ce nonce
    admin_client.app.state._kc_mock_state["last_nonce"] = nonce  # type: ignore[attr-defined]

    # 2. /auth/callback?code=...&state=...
    cb_r = admin_client.get(
        f"/auth/callback?code=auth-code-xyz&state={state}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302
    assert cb_r.headers["location"] == "/ui/x"


def test_me_returns_user_info_after_login(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client, roles=["rag-viewer"])
    _stub_secret_resolver(admin_client)

    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]

    cb_r = admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )
    assert cb_r.status_code == 302

    me_r = admin_client.get("/me")
    assert me_r.status_code == 200, me_r.text
    body = me_r.json()
    assert body["sub"] == "user-uuid-42"
    assert body["email"] == "test@example.com"
    assert body["roles"] == ["rag-viewer"]


def test_logout_clears_session_and_redirects_keycloak_logout(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    _seed_oidc_config(admin_client, admin_headers)
    _install_keycloak_mock(admin_client)
    _stub_secret_resolver(admin_client)

    # Login d'abord
    login_r = admin_client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    admin_client.app.state._kc_mock_state["last_nonce"] = params["nonce"][0]  # type: ignore[attr-defined]
    admin_client.get(
        f"/auth/callback?code=x&state={params['state'][0]}",
        follow_redirects=False,
    )

    # Logout
    out_r = admin_client.post("/auth/logout", follow_redirects=False)
    assert out_r.status_code == 302
    assert "logout" in out_r.headers["location"]
    assert "id_token_hint" in out_r.headers["location"]

    # /me ne doit plus marcher
    me_r = admin_client.get("/me")
    assert me_r.status_code == 401
```

- [ ] **Step 2: Run tests**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_auth_flow.py -v
```

Expected : `4 passed`.

- [ ] **Step 3: Iterate**

Si tests fail (probables : cookie session non transmis via TestClient, ou stub resolver pas correct), diagnostiquer en regardant les logs structlog et adapter.

- [ ] **Step 4: Lint/format**

```powershell
uv run ruff check tests/api/test_auth_flow.py
uv run ruff format tests/api/test_auth_flow.py
```

- [ ] **Step 5: Commit**

```powershell
git add backend/tests/api/test_auth_flow.py
git commit -m "test(M5a): integration auth flow (Keycloak mocké via httpx transport)"
```

---

## Task 14: Tests integration — codes erreurs

**Files:**
- Create: `backend/tests/api/test_auth_errors.py`

- [ ] **Step 1: Écrire les tests d'erreur**

```python
# backend/tests/api/test_auth_errors.py
from __future__ import annotations

import httpx
from fastapi.testclient import TestClient


def _install_failing_keycloak(client: TestClient) -> None:
    """Mock Keycloak qui répond mais avec discovery valide minimal —
    permet de tester les chemins erreur sans dépendre d'une vraie infra."""
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler)
    )


def test_auth_login_503_when_oidc_not_configured(
    admin_client: TestClient,
) -> None:
    r = admin_client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 503
    assert r.json()["error"] == "oidc_not_configured"


def test_auth_callback_400_state_missing(
    admin_client: TestClient, admin_headers: dict[str, str]
) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    # Pas de cookie state préalable → state_missing
    r = admin_client.get(
        "/auth/callback?code=x&state=fake", follow_redirects=False
    )
    assert r.status_code == 400
    assert r.json()["error"] == "oidc_state_missing"


def test_me_401_without_session(admin_client: TestClient) -> None:
    r = admin_client.get("/me")
    assert r.status_code == 401
    assert r.json()["error"] == "oidc_session_missing"


def test_refresh_401_without_session(admin_client: TestClient, admin_headers: dict[str, str]) -> None:
    admin_client.post(
        "/admin/oidc",
        headers=admin_headers,
        json={
            "issuer": "https://kc.example.com/realms/test",
            "client_id": "rag-service",
            "client_secret_ref": "kc_secret",
        },
    )
    r = admin_client.post("/auth/refresh")
    assert r.status_code == 401
    assert r.json()["error"] == "oidc_session_missing"
```

- [ ] **Step 2: Run tests**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_auth_errors.py -v
```

Expected : `4 passed`.

- [ ] **Step 3: Lint/format + commit**

```powershell
uv run ruff check tests/api/test_auth_errors.py
uv run ruff format tests/api/test_auth_errors.py
git add backend/tests/api/test_auth_errors.py
git commit -m "test(M5a): integration codes erreurs (503/400/401)"
```

---

## Task 15: Quality gate (ruff, mypy, coverage)

**Files:**
- No code changes (sauf corrections si gates échouent)

- [ ] **Step 1: ruff + format**

```powershell
cd backend
uv run ruff check src tests
uv run ruff format --check src tests
```

Expected : clean.

- [ ] **Step 2: mypy strict**

```powershell
uv run mypy src/rag
```

Expected : `Success: no issues found in N source files`. Si `authlib` génère des erreurs `attr-defined` ou `import-not-found`, vérifier qu'on a l'override `authlib.*` dans `pyproject.toml` :
```toml
[[tool.mypy.overrides]]
module = ["authlib.*"]
ignore_missing_imports = true
```

- [ ] **Step 3: pytest avec couverture**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest --cov=src/rag --cov-report=term-missing -q
```

Expected :
- Tous les tests verts (non-smoke).
- Couverture globale ≥ 95%.
- Modules M5a ≥ 90% :
  - `services/oidc.py`
  - `auth/oidc_dependency.py`
  - `api/admin_oidc.py`
  - `api/auth.py`
  - `schemas/oidc.py`

- [ ] **Step 4: Si coverage manque sur un module M5a**

Identifier les branches non couvertes via `term-missing`, ajouter des tests unit ciblés, rerun.

- [ ] **Step 5: Commit si corrections**

```powershell
git add -u
git commit -m "chore(M5a): corrections quality gate (lint/coverage)"
```

---

## Task 16: Smoke deploy LXC 303 + tag m5a-done

**Files:**
- No code changes

- [ ] **Step 1: Push dev**

```powershell
git push origin dev
```

- [ ] **Step 2: Deploy LXC 303**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Attendre build + restart + healthcheck.

- [ ] **Step 3: Smoke check API**

```powershell
curl http://192.168.10.184:8000/health
curl http://192.168.10.184:8000/version
curl http://192.168.10.184:8000/admin/oidc -H "Authorization: Bearer <RAG_MASTER_KEY_LXC>"
```

Expected :
- `/health` : `{"status":"ok"}`
- `/version` : git SHA = HEAD dev
- `/admin/oidc` (sans config) : 503 `oidc_not_configured`
- `/auth/login` (sans config) : 503 `oidc_not_configured` (redirige vers 503 JSON via le handler)

- [ ] **Step 4: Tag m5a-done**

```powershell
git tag -a m5a-done -m "M5a: OIDC backend Keycloak (config + flow + dependency)"
git push origin m5a-done
```

Expected : `* [new tag] m5a-done -> m5a-done`.

---

## Récapitulatif de couverture (cible)

| Module | Cible |
|---|---|
| `services/oidc.py` | ≥ 90% |
| `auth/oidc_dependency.py` | 100% |
| `api/admin_oidc.py` | 100% (couvert via integration) |
| `api/auth.py` | ≥ 90% (couvert via integration) |
| `schemas/oidc.py` | 100% |
| `api/errors.py` (nouveaux ajouts) | 100% |
| `config.py::fill_session_secret_fallback` | 100% |
| **Couverture globale projet** | ≥ 95% (maintenir le niveau M4c) |

## Hors scope (rappel)

- Frontend SPA (M5b)
- Refresh middleware response-wrapper (frontend appelle `/auth/refresh`)
- Multi-tenant (1 seule config OIDC)
- Audit log des login (à voir M5c+)
- Group membership Keycloak (rôles suffisent)
- Token introspection (validation locale JWKS)
- Multi-instance session sync (cookie signé stateless = OK)
- Smoke E2E réel Keycloak (reporté à M5b avec Playwright)
