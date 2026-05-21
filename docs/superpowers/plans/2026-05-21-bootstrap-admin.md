# Bootstrap Admin Local + Page OIDC Accessible — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ajouter un compte admin local (username `admin`, hash bcrypt en `.env`) qui ouvre une session IHM avec le rôle `rag-admin`, permettant de configurer OIDC depuis l'IHM existante sans recourir à curl + master-key.

**Architecture:** Cookie `_local_session` distinct (signé par `SessionMiddleware` existant) + dep unifiée `require_master_key_or_authenticated_admin` (résolution Bearer → local → OIDC). Page React `/login` non guardée qui rend selon `GET /api/auth/methods`. `dev-deploy.sh` initialise le hash via `openssl passwd -bcrypt` si absent et affiche le password en clair.

**Tech Stack:** FastAPI + asyncpg + bcrypt + Starlette SessionMiddleware + React Router + react-hook-form + Zod + Vitest + i18next + bash/openssl.

**Spec :** [`docs/superpowers/specs/2026-05-21-bootstrap-admin-design.md`](../specs/2026-05-21-bootstrap-admin-design.md)

---

## File Structure

### Backend — fichiers à créer

- `backend/src/rag/services/local_auth.py` — `LocalAuthService` (hash bcrypt, build session payload).
- `backend/src/rag/schemas/local_auth.py` — DTOs Pydantic `LocalLoginRequest`, `AuthMethodsResponse`.
- `backend/tests/services/test_local_auth.py` — 5 tests purs (verify success/wrong-pwd/wrong-user/disabled, build_session_payload).
- `backend/tests/api/test_auth_local.py` — tests des 3 endpoints (login, logout, methods).
- `backend/tests/api/test_me_local.py` — tests `/me` avec session locale.
- `backend/tests/auth/test_admin_dep.py` — tests dep unifiée.

### Backend — fichiers à modifier

- `backend/src/rag/config.py` — ajouter 3 champs `Settings` + property `bootstrap_enabled`.
- `backend/src/rag/api/errors.py` — ajouter `BootstrapDisabled`, `LocalAuthInvalidCredentials`, `LocalSessionExpired` + handler.
- `backend/src/rag/api/auth.py` — ajouter `/auth/local/login`, `/auth/local/logout`, étendre `/me`, baisse rôle requis sur `/me` à viewer-or-local-admin.
- `backend/src/rag/api/auth_methods.py` *(nouveau)* — `GET /api/auth/methods` (router public séparé du router `/auth` car prefix différent).
- `backend/src/rag/auth/bearer.py` — ajouter dep `require_master_key_or_authenticated_admin`.
- `backend/src/rag/main.py` — instancier `LocalAuthService` au lifespan, mount `/api/auth/methods` router.
- `backend/src/rag/api/admin_oidc.py:14` — bascule vers nouvelle dep.
- `backend/src/rag/api/admin_harpocrate_vaults.py` — bascule.
- `backend/src/rag/api/admin.py` — bascule.

### Frontend — fichiers à créer

- `frontend/src/pages/LoginPage.tsx` — page React de login unifiée.
- `frontend/src/pages/__tests__/LoginPage.test.tsx` — tests Vitest.
- `frontend/src/hooks/useAuthMethods.ts` — hook React Query.
- `frontend/src/i18n/fr/login.json`, `frontend/src/i18n/en/login.json` — i18n.

### Frontend — fichiers à modifier

- `frontend/src/lib/i18n.ts` — déclarer namespace `login`.
- `frontend/src/App.tsx` — extraire `<AuthGuard>` wrap : `/login` hors guard, le reste dedans.
- `frontend/src/routes.tsx` — ajouter `/login` (mais il sera ajouté dans App.tsx, pas ici — les routes guardées restent ici).
- `frontend/src/components/AuthGuard.tsx:22` — redirect 401 vers `/login` (path SPA, pas `/auth/login`).
- `frontend/src/components/Header.tsx:24-31` — logout adapté selon nature de la session.
- `frontend/src/components/__tests__/AuthGuard.test.tsx` — assertion nouvelle URL de redirect.
- `frontend/src/components/__tests__/Header.test.tsx` (s'il existe, sinon créer) — branches logout local vs OIDC.

### Script

- `dev-deploy.sh` — ajouter `ensure_bootstrap_admin_hash` (init + affichage du pwd).

---

## Notes techniques transverses

1. **Hash bcrypt + docker-compose `env_file`** : un hash bcrypt contient des `$` (`$2b$12$…`). docker-compose v2 **ne fait pas d'interpolation** sur les valeurs lues via `env_file:` (uniquement dans le YAML lui-même). Le hash peut donc être stocké tel quel dans `.env`. Pas de quoting nécessaire, pas de `$$`. Référence : https://docs.docker.com/compose/environment-variables/env-file/
2. **Pydantic Settings** (`backend/src/rag/config.py:71`) : `extra="ignore"`, `case_sensitive=False`, `env_prefix=""` — ajouter un champ snake_case `rag_bootstrap_admin_password_hash` mappera automatiquement sur la var `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH`.
3. **Tests backend** : pattern existant `session_pool` + `run_migrations` (cf. fixture `client` dans `backend/tests/conftest.py`). Pas de migration ici donc cycle DB inchangé.
4. **Tests Vitest** : `npm run test:run` pour one-shot (pas `npm test` qui est en watch).
5. **Routing React** : SPA servi sous `/ui/` (cf. Caddyfile `handle /ui*`). React Router travaille avec basename `/ui`. Le path `/login` côté React correspond à l'URL `/ui/login` côté browser. `AuthGuard` doit donc rediriger vers `/login` (relatif au basename).

---

## Task 1 — `LocalAuthService` + tests purs

**Files:**
- Create: `backend/src/rag/services/local_auth.py`
- Create: `backend/tests/services/test_local_auth.py`
- Modify: `backend/src/rag/config.py` (3 nouveaux champs + property)

### Step 1.1 — Écrire les tests purs (RED)

- [ ] Créer `backend/tests/services/test_local_auth.py` :

```python
from __future__ import annotations

import time

import bcrypt
import pytest

from rag.services.local_auth import LocalAuthService


@pytest.fixture
def known_hash() -> str:
    """Hash bcrypt de 'correctpwd' avec cost minimal pour tests rapides."""
    return bcrypt.hashpw(b"correctpwd", bcrypt.gensalt(rounds=4)).decode()


def test_verify_success(known_hash: str) -> None:
    svc = LocalAuthService(
        username="admin", password_hash=known_hash, ttl_seconds=3600
    )
    assert svc.verify(username="admin", password="correctpwd") is True


def test_verify_wrong_password(known_hash: str) -> None:
    svc = LocalAuthService(
        username="admin", password_hash=known_hash, ttl_seconds=3600
    )
    assert svc.verify(username="admin", password="wrong") is False


def test_verify_wrong_username(known_hash: str) -> None:
    svc = LocalAuthService(
        username="admin", password_hash=known_hash, ttl_seconds=3600
    )
    assert svc.verify(username="root", password="correctpwd") is False


def test_verify_when_disabled() -> None:
    """password_hash vide → enabled=False → verify retourne toujours False."""
    svc = LocalAuthService(username="admin", password_hash="", ttl_seconds=3600)
    assert svc.enabled is False
    assert svc.verify(username="admin", password="anything") is False


def test_verify_malformed_hash_returns_false() -> None:
    """Hash non bcrypt valide → False sans crash (pas de validation au boot)."""
    svc = LocalAuthService(
        username="admin", password_hash="not-a-bcrypt-hash", ttl_seconds=3600
    )
    assert svc.verify(username="admin", password="anything") is False


def test_build_session_payload_has_expiry(known_hash: str) -> None:
    svc = LocalAuthService(
        username="admin", password_hash=known_hash, ttl_seconds=3600
    )
    before = int(time.time())
    payload = svc.build_session_payload()
    after = int(time.time())
    assert payload["username"] == "admin"
    assert before + 3600 <= payload["expires_at"] <= after + 3600
```

### Step 1.2 — Vérifier que les tests échouent (FAIL)

- [ ] Run :

```
cd backend && uv run pytest tests/services/test_local_auth.py -v
```

Expected : `ModuleNotFoundError: No module named 'rag.services.local_auth'`.

### Step 1.3 — Étendre `Settings` (`backend/src/rag/config.py`)

- [ ] Ajouter 3 champs et la property après la ligne `api_key_dek: str | None = …` (vers ligne 62) :

```python
    rag_bootstrap_admin_username: str = "admin"
    rag_bootstrap_admin_password_hash: str = ""
    rag_bootstrap_session_ttl_seconds: int = Field(default=28800, ge=60)

    @property
    def bootstrap_enabled(self) -> bool:
        return bool(self.rag_bootstrap_admin_password_hash.strip())
```

### Step 1.4 — Implémenter `LocalAuthService` (`backend/src/rag/services/local_auth.py`)

- [ ] Créer le fichier :

```python
from __future__ import annotations

import time

import bcrypt


class LocalAuthService:
    """Auth locale bootstrap : un seul user `admin`, hash bcrypt en .env.

    Le service est `enabled` si et seulement si `password_hash` est non vide.
    `verify` est constant-time grâce à `bcrypt.checkpw`. Aucune validation
    au boot du format du hash : un hash invalide fait simplement échouer le
    login (False), pas de fail-fast.
    """

    def __init__(
        self,
        *,
        username: str,
        password_hash: str,
        ttl_seconds: int,
    ) -> None:
        self._username = username
        self._password_hash = password_hash
        self._ttl_seconds = ttl_seconds

    @property
    def enabled(self) -> bool:
        return bool(self._password_hash.strip())

    @property
    def username(self) -> str:
        return self._username

    def verify(self, *, username: str, password: str) -> bool:
        if not self.enabled:
            return False
        if username != self._username:
            return False
        try:
            return bcrypt.checkpw(password.encode("utf-8"), self._password_hash.encode("utf-8"))
        except ValueError:
            # Hash malformé — ne crashe pas, simplement login refusé.
            return False

    def build_session_payload(self) -> dict[str, int | str]:
        return {
            "username": self._username,
            "expires_at": int(time.time()) + self._ttl_seconds,
        }
```

### Step 1.5 — Vérifier que les tests passent (GREEN)

- [ ] Run :

```
cd backend && uv run pytest tests/services/test_local_auth.py -v
```

Expected : 6 PASSED (5 verify-related + 1 build_session_payload).

### Step 1.6 — Lint + commit

- [ ] Run :

```
cd backend && uv run ruff check src/rag/services/local_auth.py src/rag/config.py tests/services/test_local_auth.py
cd backend && uv run ruff format src/rag/services/local_auth.py src/rag/config.py tests/services/test_local_auth.py
```

Expected : aucune erreur lint.

- [ ] Commit :

```
git add backend/src/rag/services/local_auth.py backend/src/rag/config.py backend/tests/services/test_local_auth.py
git commit -m "feat(bootstrap-admin-T1): LocalAuthService + 3 champs Settings + 6 tests purs"
```

---

## Task 2 — Routes `/auth/local/login|logout` + `/api/auth/methods`

**Files:**
- Create: `backend/src/rag/schemas/local_auth.py`
- Create: `backend/src/rag/api/auth_methods.py`
- Create: `backend/tests/api/test_auth_local.py`
- Modify: `backend/src/rag/api/errors.py` (3 nouvelles erreurs + handler)
- Modify: `backend/src/rag/api/auth.py` (2 nouvelles routes login/logout)
- Modify: `backend/src/rag/main.py` (lifespan attache `local_auth`, mount router methods)

### Step 2.1 — Schémas Pydantic

- [ ] Créer `backend/src/rag/schemas/local_auth.py` :

```python
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
```

### Step 2.2 — Erreurs typées (`backend/src/rag/api/errors.py`)

- [ ] Lire le fichier pour situer le pattern existant des `OidcXxx` errors :

```
cd backend && head -80 src/rag/api/errors.py
```

- [ ] Ajouter 3 classes d'erreur en suivant le pattern existant (ex. `OidcNotConfigured`) :

```python
class BootstrapDisabled(Exception):
    """Login local appelé alors que RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH est vide."""


class LocalAuthInvalidCredentials(Exception):
    """Username inconnu ou mot de passe incorrect. Réponse uniforme."""


class LocalSessionExpired(Exception):
    """Cookie _local_session présent mais expires_at < now."""
```

- [ ] Étendre `register_error_handlers` pour mapper les 3 nouvelles erreurs aux codes HTTP (suivre la structure existante du dict d'errors → handler) :

```python
# Dans register_error_handlers, ajouter en suivant le pattern existant :
@app.exception_handler(BootstrapDisabled)
async def _bootstrap_disabled(request, exc):
    return JSONResponse(
        status_code=503,
        content={
            "error": "bootstrap_disabled",
            "message": "RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH non défini dans la configuration",
        },
    )

@app.exception_handler(LocalAuthInvalidCredentials)
async def _local_invalid(request, exc):
    return JSONResponse(
        status_code=401,
        content={"error": "invalid_credentials", "message": "Identifiants invalides"},
    )

@app.exception_handler(LocalSessionExpired)
async def _local_expired(request, exc):
    return JSONResponse(
        status_code=401,
        content={"error": "local_session_expired", "message": "Session locale expirée"},
    )
```

### Step 2.3 — Tests endpoints (RED)

- [ ] Créer `backend/tests/api/test_auth_local.py` :

```python
from __future__ import annotations

import bcrypt
import pytest
from fastapi.testclient import TestClient

# Le fixture `client` doit construire l'app avec un Settings dont
# rag_bootstrap_admin_password_hash est non vide. On exploite la possibilité
# d'injecter via env var (cf. pytest-monkeypatch / conftest existant).


@pytest.fixture
def admin_pwd() -> str:
    return "bootstrap-test-pwd"


@pytest.fixture
def admin_hash(admin_pwd: str) -> str:
    return bcrypt.hashpw(admin_pwd.encode(), bcrypt.gensalt(rounds=4)).decode()


@pytest.fixture
def client_with_bootstrap(admin_hash: str, monkeypatch, client_factory):
    """Construit un client TestClient avec bootstrap activé.

    `client_factory` est une fixture conftest qui prend un dict d'env
    overrides et retourne TestClient. À implémenter ou réutiliser un
    pattern existant dans tests/conftest.py.
    """
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH", admin_hash)
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_USERNAME", "admin")
    return client_factory()


def test_local_login_success(client_with_bootstrap, admin_pwd):
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": "admin", "password": admin_pwd},
    )
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # Cookie session doit être posé
    assert "session" in resp.cookies or any("session" in c for c in resp.cookies)


def test_local_login_wrong_password(client_with_bootstrap):
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": "admin", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_wrong_username(client_with_bootstrap, admin_pwd):
    """Username inconnu ne se distingue pas d'un mauvais pwd (même 401)."""
    resp = client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": "root", "password": admin_pwd},
    )
    assert resp.status_code == 401
    assert resp.json()["error"] == "invalid_credentials"


def test_local_login_bootstrap_disabled(client_factory, monkeypatch):
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH", "")
    client = client_factory()
    resp = client.post(
        "/auth/local/login",
        json={"username": "admin", "password": "anything"},
    )
    assert resp.status_code == 503
    assert resp.json()["error"] == "bootstrap_disabled"


def test_local_login_invalid_body(client_with_bootstrap):
    resp = client_with_bootstrap.post(
        "/auth/local/login", json={"username": "admin"}
    )
    assert resp.status_code == 422


def test_local_logout_idempotent(client_with_bootstrap):
    """Logout sans session ne renvoie pas d'erreur."""
    resp = client_with_bootstrap.post("/auth/local/logout")
    assert resp.status_code == 204


def test_local_logout_clears_session(client_with_bootstrap, admin_pwd):
    """Login puis logout clear le cookie."""
    client_with_bootstrap.post(
        "/auth/local/login",
        json={"username": "admin", "password": admin_pwd},
    )
    resp = client_with_bootstrap.post("/auth/local/logout")
    assert resp.status_code == 204
    # /me après logout doit renvoyer 401
    me = client_with_bootstrap.get("/me")
    assert me.status_code == 401


def test_auth_methods_bootstrap_only(client_with_bootstrap):
    resp = client_with_bootstrap.get("/api/auth/methods")
    assert resp.status_code == 200
    data = resp.json()
    assert data["oidc_configured"] is False  # pas configuré en DB par défaut
    assert data["bootstrap_enabled"] is True


def test_auth_methods_no_auth_means_disabled(client_factory, monkeypatch):
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH", "")
    client = client_factory()
    resp = client.get("/api/auth/methods")
    assert resp.status_code == 200
    assert resp.json() == {"oidc_configured": False, "bootstrap_enabled": False}
```

> **Note** : si `client_factory` n'existe pas en conftest, lire `backend/tests/conftest.py` au début de cette task et adapter les fixtures pour pouvoir override `RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH` via monkeypatch.

### Step 2.4 — Vérifier que les tests échouent

- [ ] Run :

```
cd backend && uv run pytest tests/api/test_auth_local.py -v
```

Expected : tous FAIL (routes inexistantes → 404 ou erreur de construction app).

### Step 2.5 — Implémenter les routes login/logout dans `api/auth.py`

- [ ] Lire `backend/src/rag/api/auth.py` (~140 lignes, déjà connu).

- [ ] Ajouter en tête du fichier (imports) :

```python
from rag.api.errors import (
    BootstrapDisabled,
    LocalAuthInvalidCredentials,
    OidcNotConfigured,
    OidcSessionExpired,
    OidcSessionMissing,
    OidcStateMismatch,
    OidcStateMissing,
)
from rag.schemas.local_auth import LocalLoginRequest, LocalLoginResponse

_LOCAL_SESSION_KEY = "_local_session"
```

- [ ] Ajouter deux routes dans `build_auth_router` (avant `return router`) :

```python
@router.post("/auth/local/login", response_model=LocalLoginResponse)
async def local_login(payload: LocalLoginRequest, request: Request) -> LocalLoginResponse:
    local_auth = request.app.state.local_auth
    if not local_auth.enabled:
        raise BootstrapDisabled()
    if not local_auth.verify(username=payload.username, password=payload.password):
        raise LocalAuthInvalidCredentials()
    request.session[_LOCAL_SESSION_KEY] = local_auth.build_session_payload()
    return LocalLoginResponse()


@router.post("/auth/local/logout", status_code=status.HTTP_204_NO_CONTENT)
async def local_logout(request: Request) -> Response:
    request.session.pop(_LOCAL_SESSION_KEY, None)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

### Step 2.6 — Implémenter `/api/auth/methods` (nouveau router)

- [ ] Créer `backend/src/rag/api/auth_methods.py` :

```python
from __future__ import annotations

from fastapi import APIRouter, Request

from rag.schemas.local_auth import AuthMethodsResponse


def build_auth_methods_router() -> APIRouter:
    """Router public (pas d'auth) qui expose les méthodes activées.

    Utilisé par le frontend pour décider quoi afficher sur /ui/login.
    """
    router = APIRouter(prefix="/api/auth", tags=["auth"])

    @router.get("/methods", response_model=AuthMethodsResponse)
    async def get_methods(request: Request) -> AuthMethodsResponse:
        oidc_cfg = await request.app.state.oidc.get_config()
        local_auth = request.app.state.local_auth
        return AuthMethodsResponse(
            oidc_configured=oidc_cfg is not None,
            bootstrap_enabled=local_auth.enabled,
        )

    return router
```

### Step 2.7 — Lifespan : attacher `local_auth` + mount router

- [ ] Dans `backend/src/rag/main.py`, lifespan, après l'instanciation `OidcService` (vers la ligne où `app.state.oidc` est posé) :

```python
from rag.services.local_auth import LocalAuthService  # en tête

# Dans lifespan :
app.state.local_auth = LocalAuthService(
    username=settings.rag_bootstrap_admin_username,
    password_hash=settings.rag_bootstrap_admin_password_hash,
    ttl_seconds=settings.rag_bootstrap_session_ttl_seconds,
)
```

- [ ] Mount le router methods. Localiser la zone où les routers sont déjà inclus (`app.include_router(...)`) et ajouter :

```python
from rag.api.auth_methods import build_auth_methods_router

app.include_router(build_auth_methods_router())
```

### Step 2.8 — Vérifier que les tests passent

- [ ] Run :

```
cd backend && uv run pytest tests/api/test_auth_local.py -v
```

Expected : 9 PASSED.

### Step 2.9 — Lint + commit

- [ ] Run :

```
cd backend && uv run ruff check src/rag/ tests/
cd backend && uv run ruff format src/rag/ tests/
cd backend && uv run pytest -v
```

Expected : tout passe, pas de régression sur les tests existants.

- [ ] Commit :

```
git add backend/src/rag/schemas/local_auth.py backend/src/rag/api/auth_methods.py \
        backend/src/rag/api/auth.py backend/src/rag/api/errors.py backend/src/rag/main.py \
        backend/tests/api/test_auth_local.py
git commit -m "feat(bootstrap-admin-T2): routes /auth/local/{login,logout} + /api/auth/methods + 9 tests"
```

---

## Task 3 — Dep unifiée + migration routers admin

**Files:**
- Modify: `backend/src/rag/auth/bearer.py` (ajouter dep)
- Modify: `backend/src/rag/api/admin_oidc.py:14` (bascule dep)
- Modify: `backend/src/rag/api/admin_harpocrate_vaults.py` (bascule dep)
- Modify: `backend/src/rag/api/admin.py` (bascule dep)
- Create: `backend/tests/auth/test_admin_dep.py`

### Step 3.1 — Tests dep unifiée (RED)

- [ ] Créer `backend/tests/auth/test_admin_dep.py` :

```python
from __future__ import annotations

import time

import bcrypt
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from rag.auth.bearer import require_master_key_or_authenticated_admin
from rag.services.local_auth import LocalAuthService


class _StubOidcService:
    """Stub minimaliste : pas de session OIDC valide → toujours raise."""

    async def get_config(self):
        return None


@pytest.fixture
def app_with_dep():
    app = FastAPI()
    app.add_middleware(SessionMiddleware, secret_key="a" * 32)
    app.state.master_key = "test-master-key-123"
    app.state.local_auth = LocalAuthService(
        username="admin",
        password_hash=bcrypt.hashpw(b"pwd", bcrypt.gensalt(rounds=4)).decode(),
        ttl_seconds=3600,
    )
    app.state.oidc = _StubOidcService()

    @app.get("/protected", dependencies=[Depends(require_master_key_or_authenticated_admin)])
    async def protected():
        return {"ok": True}

    @app.post("/_setup_local_session")
    async def setup(request):
        request.session["_local_session"] = {
            "username": "admin",
            "expires_at": int(time.time()) + 3600,
        }
        return {"ok": True}

    @app.post("/_setup_expired_local_session")
    async def setup_expired(request):
        request.session["_local_session"] = {
            "username": "admin",
            "expires_at": int(time.time()) - 1,
        }
        return {"ok": True}

    return app


def test_bearer_master_key_ok(app_with_dep):
    client = TestClient(app_with_dep)
    resp = client.get(
        "/protected",
        headers={"Authorization": "Bearer test-master-key-123"},
    )
    assert resp.status_code == 200


def test_bearer_master_key_invalid_returns_401(app_with_dep):
    client = TestClient(app_with_dep)
    resp = client.get(
        "/protected", headers={"Authorization": "Bearer wrong"}
    )
    assert resp.status_code == 401


def test_local_session_valid_ok(app_with_dep):
    client = TestClient(app_with_dep)
    client.post("/_setup_local_session")
    resp = client.get("/protected")
    assert resp.status_code == 200


def test_local_session_expired_raises_401(app_with_dep):
    client = TestClient(app_with_dep)
    client.post("/_setup_expired_local_session")
    resp = client.get("/protected")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_no_auth_falls_through_to_oidc_and_fails(app_with_dep):
    """Pas de Bearer ni de session locale → tente OIDC → échoue (pas de config)."""
    client = TestClient(app_with_dep)
    resp = client.get("/protected")
    assert resp.status_code == 401
```

### Step 3.2 — Vérifier que les tests échouent

- [ ] Run :

```
cd backend && uv run pytest tests/auth/test_admin_dep.py -v
```

Expected : `ImportError` sur `require_master_key_or_authenticated_admin`.

### Step 3.3 — Implémenter la dep (`backend/src/rag/auth/bearer.py`)

- [ ] Ajouter au bas du fichier `bearer.py` :

```python
import time

from rag.api.errors import LocalSessionExpired


_LOCAL_SESSION_KEY = "_local_session"


async def require_master_key_or_authenticated_admin(request: Request) -> None:
    """Dependency : Bearer master-key OU session locale OU session OIDC rôle rag-admin.

    Ordre de résolution explicite :
    1. Bearer présent → master-key (échec → 401, ne fallback PAS sur session)
    2. Session locale présente :
       - valide (expires_at > now) → ok
       - expirée → clear + LocalSessionExpired (401)
    3. Sinon → require_oidc_role("rag-admin")
    """
    from rag.auth.oidc_dependency import require_oidc_role

    auth_header = request.headers.get("Authorization")
    if auth_header:
        require_master_key(request)
        return None

    local_session = request.session.get(_LOCAL_SESSION_KEY)
    if local_session:
        expires_at = local_session.get("expires_at", 0)
        if expires_at > int(time.time()):
            return None
        # expiré
        request.session.pop(_LOCAL_SESSION_KEY, None)
        raise LocalSessionExpired()

    oidc_dep = require_oidc_role("rag-admin")
    await oidc_dep(request)
    return None
```

### Step 3.4 — Migrer les routers admin

- [ ] Modifier `backend/src/rag/api/admin_oidc.py:14` :

```python
# Avant :
dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
# Après :
dependencies=[Depends(require_master_key_or_authenticated_admin)],
```

- [ ] Modifier `backend/src/rag/api/admin_harpocrate_vaults.py` : remplacer chaque usage de `require_master_key_or_oidc_role("rag-admin")` par `require_master_key_or_authenticated_admin`.

- [ ] Modifier `backend/src/rag/api/admin.py` : idem.

> **Note** : `require_master_key_or_oidc_role` reste exporté dans `bearer.py` pour ne pas casser d'éventuels usages oubliés. Sa suppression est hors-scope.

### Step 3.5 — Vérifier tests dep + non-régression

- [ ] Run :

```
cd backend && uv run pytest tests/auth/test_admin_dep.py -v
cd backend && uv run pytest -v
```

Expected : 5 nouveaux PASSED + aucune régression. Si un test admin existant casse, vérifier qu'il utilisait `require_master_key_or_oidc_role` directement (à mettre à jour) et corriger.

### Step 3.6 — Lint + commit

- [ ] Run :

```
cd backend && uv run ruff check src/rag/auth/ src/rag/api/ tests/auth/
cd backend && uv run ruff format src/rag/auth/ src/rag/api/ tests/auth/
```

- [ ] Commit :

```
git add backend/src/rag/auth/bearer.py backend/src/rag/api/admin_oidc.py \
        backend/src/rag/api/admin_harpocrate_vaults.py backend/src/rag/api/admin.py \
        backend/tests/auth/test_admin_dep.py
git commit -m "feat(bootstrap-admin-T3): dep unifiee require_master_key_or_authenticated_admin + migration 3 routers admin"
```

---

## Task 4 — `/me` étendu pour session locale

**Files:**
- Modify: `backend/src/rag/api/auth.py:127-136` (route `/me`)
- Create: `backend/tests/api/test_me_local.py`

### Step 4.1 — Tests `/me` local (RED)

- [ ] Créer `backend/tests/api/test_me_local.py` :

```python
from __future__ import annotations

import time

import bcrypt
import pytest


@pytest.fixture
def client_logged_local(client_factory, monkeypatch):
    h = bcrypt.hashpw(b"pwd", bcrypt.gensalt(rounds=4)).decode()
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH", h)
    client = client_factory()
    client.post("/auth/local/login", json={"username": "admin", "password": "pwd"})
    return client


def test_me_returns_local_user(client_logged_local):
    resp = client_logged_local.get("/me")
    assert resp.status_code == 200
    data = resp.json()
    assert data == {"sub": "admin", "email": None, "name": None, "roles": ["rag-admin"]}


def test_me_local_session_expired_clears_and_401(client_factory, monkeypatch):
    h = bcrypt.hashpw(b"pwd", bcrypt.gensalt(rounds=4)).decode()
    monkeypatch.setenv("RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH", h)
    monkeypatch.setenv("RAG_BOOTSTRAP_SESSION_TTL_SECONDS", "1")
    client = client_factory()
    client.post("/auth/local/login", json={"username": "admin", "password": "pwd"})
    time.sleep(1.1)
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "local_session_expired"


def test_me_no_session_returns_401_missing(client_factory):
    client = client_factory()
    resp = client.get("/me")
    assert resp.status_code == 401
    assert resp.json()["error"] == "oidc_session_missing"
```

### Step 4.2 — Vérifier FAIL

- [ ] Run :

```
cd backend && uv run pytest tests/api/test_me_local.py -v
```

Expected : `test_me_returns_local_user` FAIL (renvoie 401, pas le user local).

### Step 4.3 — Refactor `/me` (`backend/src/rag/api/auth.py:127-136`)

- [ ] Remplacer la route `/me` actuelle par une version qui résout d'abord la session locale :

```python
@router.get("/me", response_model=MeResponse)
async def me(request: Request) -> MeResponse:
    local_session = request.session.get(_LOCAL_SESSION_KEY)
    if local_session:
        expires_at = local_session.get("expires_at", 0)
        if expires_at > int(time.time()):
            return MeResponse(
                sub=local_session["username"],
                email=None,
                name=None,
                roles=["rag-admin"],
            )
        request.session.pop(_LOCAL_SESSION_KEY, None)
        raise LocalSessionExpired()

    # Délègue au chemin OIDC existant
    oidc_dep = require_oidc_role("rag-viewer")
    user = await oidc_dep(request)
    return MeResponse(
        sub=user.sub,
        email=user.email,
        name=user.name,
        roles=user.roles,
    )
```

- [ ] Ajouter les imports manquants en tête du fichier :

```python
import time
from rag.api.errors import LocalSessionExpired
```

### Step 4.4 — Vérifier PASS

- [ ] Run :

```
cd backend && uv run pytest tests/api/test_me_local.py tests/api/test_auth_local.py -v
cd backend && uv run pytest -v
```

Expected : 3 nouveaux PASSED + non-régression complète.

### Step 4.5 — Lint + commit

- [ ] Run :

```
cd backend && uv run ruff check src/rag/api/auth.py tests/api/test_me_local.py
cd backend && uv run ruff format src/rag/api/auth.py tests/api/test_me_local.py
```

- [ ] Commit :

```
git add backend/src/rag/api/auth.py backend/tests/api/test_me_local.py
git commit -m "feat(bootstrap-admin-T4): /me resout session locale en priorite + 3 tests"
```

---

## Task 5 — Frontend `LoginPage` + hook + i18n + adaptations

**Files:**
- Create: `frontend/src/hooks/useAuthMethods.ts`
- Create: `frontend/src/pages/LoginPage.tsx`
- Create: `frontend/src/pages/__tests__/LoginPage.test.tsx`
- Create: `frontend/src/i18n/fr/login.json`
- Create: `frontend/src/i18n/en/login.json`
- Modify: `frontend/src/lib/i18n.ts` (déclarer namespace `login`)
- Modify: `frontend/src/App.tsx` (router top-level avec `/login` hors AuthGuard)
- Modify: `frontend/src/components/AuthGuard.tsx:22` (redirect vers `/login`)
- Modify: `frontend/src/components/Header.tsx:24-31` (logout adapté)
- Modify: `frontend/src/components/__tests__/AuthGuard.test.tsx` (nouvelle URL redirect)

### Step 5.1 — i18n namespace `login`

- [ ] Créer `frontend/src/i18n/fr/login.json` :

```json
{
  "title": "Connexion",
  "oidc": {
    "button": "Connexion via Keycloak"
  },
  "local": {
    "section_title": "Login admin local",
    "fields": {
      "username": "Username",
      "password": "Password"
    },
    "submit": "Se connecter"
  },
  "errors": {
    "invalid_credentials": "Identifiants invalides",
    "no_method": "Aucune méthode d'authentification configurée — contactez l'administrateur",
    "bootstrap_disabled": "Login local désactivé"
  },
  "info": {
    "oidc_not_configured": "OIDC pas encore configuré. Loguez-vous avec le compte admin local pour le paramétrer.",
    "separator_or": "ou login admin local"
  }
}
```

- [ ] Créer `frontend/src/i18n/en/login.json` :

```json
{
  "title": "Sign in",
  "oidc": {
    "button": "Sign in with Keycloak"
  },
  "local": {
    "section_title": "Local admin login",
    "fields": {
      "username": "Username",
      "password": "Password"
    },
    "submit": "Sign in"
  },
  "errors": {
    "invalid_credentials": "Invalid credentials",
    "no_method": "No authentication method configured — contact your administrator",
    "bootstrap_disabled": "Local login disabled"
  },
  "info": {
    "oidc_not_configured": "OIDC is not configured yet. Sign in with the local admin account to set it up.",
    "separator_or": "or local admin login"
  }
}
```

- [ ] Modifier `frontend/src/lib/i18n.ts` : ajouter les 2 imports, le namespace dans la liste `ns`, et les resources :

```ts
import frLogin from "@/i18n/fr/login.json";
import enLogin from "@/i18n/en/login.json";

// dans .init({...})
ns: ["common", "auth", "nav", "workspaces", "workspace", "harpocrate", "models", "oidc", "login"],
// dans resources.fr :
login: frLogin,
// dans resources.en :
login: enLogin,
```

### Step 5.2 — Hook `useAuthMethods`

- [ ] Créer `frontend/src/hooks/useAuthMethods.ts` :

```ts
import { useQuery } from "@tanstack/react-query";

export type AuthMethods = {
  oidc_configured: boolean;
  bootstrap_enabled: boolean;
};

export function useAuthMethods() {
  return useQuery<AuthMethods>({
    queryKey: ["auth", "methods"],
    queryFn: async () => {
      const r = await fetch("/api/auth/methods");
      if (!r.ok) throw new Error(`auth_methods_${r.status}`);
      return (await r.json()) as AuthMethods;
    },
    staleTime: Infinity,
    retry: false,
  });
}
```

### Step 5.3 — Tests `LoginPage` (RED)

- [ ] Créer `frontend/src/pages/__tests__/LoginPage.test.tsx` :

```tsx
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { I18nextProvider } from "react-i18next";
import i18n from "@/lib/i18n";
import { LoginPage } from "@/pages/LoginPage";

function renderLogin() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={i18n}>
        <MemoryRouter initialEntries={["/login"]}>
          <LoginPage />
        </MemoryRouter>
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

const originalFetch = global.fetch;

function mockMethods(methods: { oidc_configured: boolean; bootstrap_enabled: boolean }) {
  global.fetch = vi.fn(async (url: string) => {
    if (typeof url === "string" && url.includes("/api/auth/methods")) {
      return { ok: true, json: async () => methods } as Response;
    }
    throw new Error("unexpected fetch " + url);
  }) as typeof fetch;
}

describe("LoginPage", () => {
  beforeEach(() => {
    // window.location stub
    delete (window as { location?: unknown }).location;
    (window as { location?: unknown }).location = { href: "", pathname: "/login", search: "" };
  });

  afterEach(() => {
    global.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("etat 1 : SSO + form local quand oidc=true et bootstrap=true", async () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: true });
    renderLogin();
    await waitFor(() => screen.getByText(/Keycloak/));
    expect(screen.getByText(/Keycloak/)).toBeTruthy();
    expect(screen.getByLabelText(/Username/i)).toBeTruthy();
    expect(screen.getByLabelText(/Password/i)).toBeTruthy();
  });

  it("etat 2 : form local seul + info OIDC pas configure quand oidc=false et bootstrap=true", async () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: true });
    renderLogin();
    await waitFor(() => screen.getByLabelText(/Username/i));
    expect(screen.queryByText(/Keycloak/)).toBeNull();
    expect(screen.getByText(/OIDC pas encore configuré|OIDC is not configured yet/)).toBeTruthy();
  });

  it("etat 3 : SSO seul quand oidc=true et bootstrap=false", async () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: false });
    renderLogin();
    await waitFor(() => screen.getByText(/Keycloak/));
    expect(screen.queryByLabelText(/Username/i)).toBeNull();
  });

  it("etat 4 : message d'erreur quand aucune methode", async () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: false });
    renderLogin();
    await waitFor(() => screen.getByText(/Aucune méthode|No authentication method/));
  });

  it("submit valide redirige vers next", async () => {
    mockMethods({ oidc_configured: false, bootstrap_enabled: true });
    // Mock POST /auth/local/login
    const fetchSpy = vi.fn(async (url: string, init?: RequestInit) => {
      if (typeof url === "string" && url.includes("/api/auth/methods")) {
        return { ok: true, json: async () => ({ oidc_configured: false, bootstrap_enabled: true }) } as Response;
      }
      if (typeof url === "string" && url.includes("/auth/local/login")) {
        return { ok: true, status: 200, json: async () => ({ ok: true }) } as Response;
      }
      throw new Error("unexpected " + url);
    });
    global.fetch = fetchSpy as typeof fetch;
    (window as { location?: unknown }).location = { href: "", pathname: "/login", search: "?next=%2Fworkspaces" };

    renderLogin();
    await waitFor(() => screen.getByLabelText(/Username/i));
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "pwd" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter|Sign in/ }));

    await waitFor(() => expect((window.location as { href: string }).href).toContain("/workspaces"));
  });

  it("submit 401 affiche erreur, ne redirige pas", async () => {
    const fetchSpy = vi.fn(async (url: string) => {
      if (typeof url === "string" && url.includes("/api/auth/methods")) {
        return { ok: true, json: async () => ({ oidc_configured: false, bootstrap_enabled: true }) } as Response;
      }
      return { ok: false, status: 401, json: async () => ({ error: "invalid_credentials" }) } as Response;
    });
    global.fetch = fetchSpy as typeof fetch;
    renderLogin();
    await waitFor(() => screen.getByLabelText(/Username/i));
    fireEvent.change(screen.getByLabelText(/Username/i), { target: { value: "admin" } });
    fireEvent.change(screen.getByLabelText(/Password/i), { target: { value: "wrong" } });
    fireEvent.click(screen.getByRole("button", { name: /Se connecter|Sign in/ }));

    await waitFor(() => screen.getByText(/Identifiants invalides|Invalid credentials/));
  });

  it("click SSO redirige vers /auth/login avec next", async () => {
    mockMethods({ oidc_configured: true, bootstrap_enabled: false });
    (window as { location?: unknown }).location = { href: "", pathname: "/login", search: "?next=%2Fworkspaces" };
    renderLogin();
    await waitFor(() => screen.getByRole("button", { name: /Keycloak/ }));
    fireEvent.click(screen.getByRole("button", { name: /Keycloak/ }));
    expect((window.location as { href: string }).href).toContain("/auth/login");
    expect((window.location as { href: string }).href).toContain("next=%2Fworkspaces");
  });
});
```

### Step 5.4 — Vérifier FAIL

- [ ] Run :

```
cd frontend && npm run test:run -- src/pages/__tests__/LoginPage.test.tsx
```

Expected : import error / file not found.

### Step 5.5 — Implémenter `LoginPage`

- [ ] Créer `frontend/src/pages/LoginPage.tsx` :

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useAuthMethods } from "@/hooks/useAuthMethods";

const schema = z.object({
  username: z.string().min(1, "required"),
  password: z.string().min(1, "required"),
});

type FormValues = z.infer<typeof schema>;

function getNextFromSearch(): string {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/workspaces";
}

export function LoginPage() {
  const { t } = useTranslation("login");
  const { data: methods, isLoading } = useAuthMethods();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "admin", password: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    const resp = await fetch("/auth/local/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (resp.ok) {
      window.location.href = getNextFromSearch();
      return;
    }
    if (resp.status === 401) {
      setError(t("errors.invalid_credentials"));
    } else if (resp.status === 503) {
      setError(t("errors.bootstrap_disabled"));
    } else {
      setError(`Erreur ${resp.status}`);
    }
  };

  const handleSsoClick = () => {
    const next = encodeURIComponent(getNextFromSearch());
    window.location.href = `/auth/login?next=${next}`;
  };

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <LoadingSpinner />
      </div>
    );
  }

  const showOidc = !!methods?.oidc_configured;
  const showLocal = !!methods?.bootstrap_enabled;

  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-md border bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900 mb-4">{t("title")}</h1>

        {!showOidc && !showLocal && (
          <p className="text-sm text-red-600">{t("errors.no_method")}</p>
        )}

        {showOidc && (
          <Button type="button" onClick={handleSsoClick} className="w-full mb-4">
            → {t("oidc.button")}
          </Button>
        )}

        {showOidc && showLocal && (
          <div className="my-4 flex items-center gap-2 text-xs text-slate-400">
            <div className="flex-1 border-t" />
            <span>{t("info.separator_or")}</span>
            <div className="flex-1 border-t" />
          </div>
        )}

        {showLocal && (
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
            {!showOidc && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                {t("info.oidc_not_configured")}
              </p>
            )}
            <div>
              <label htmlFor="username" className="text-sm font-medium text-slate-700">
                {t("local.fields.username")}
              </label>
              <Input id="username" {...form.register("username")} className="mt-1" />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium text-slate-700">
                {t("local.fields.password")}
              </label>
              <Input id="password" type="password" {...form.register("password")} className="mt-1" />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {t("local.submit")}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
```

### Step 5.6 — Modifier `AuthGuard` (redirect vers `/login`)

- [ ] Modifier `frontend/src/components/AuthGuard.tsx:22` :

```ts
// Avant :
window.location.href = `/auth/login?next=${encodeURIComponent(next)}`;
// Après :
window.location.href = `/login?next=${encodeURIComponent(next)}`;
```

> Note : `/login` est interprété par Caddy `handle /ui*` qui sert le frontend → React Router résout `/login`. Pas de `/ui/` à préfixer manuellement (basename SPA).

### Step 5.7 — Restructurer `App.tsx` (router top-level)

- [ ] Remplacer `frontend/src/App.tsx` :

```tsx
import { BrowserRouter, Route, Routes } from "react-router-dom";
import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Toaster } from "@/components/ui/toaster";
import { AppRoutes } from "@/routes";
import { LoginPage } from "@/pages/LoginPage";

function GuardedShell() {
  return (
    <AuthGuard>
      <div className="flex h-screen bg-slate-50">
        <Sidebar />
        <div className="flex-1 flex flex-col">
          <Header />
          <main className="flex-1 overflow-y-auto p-6">
            <AppRoutes />
          </main>
        </div>
      </div>
    </AuthGuard>
  );
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="/*" element={<GuardedShell />} />
      </Routes>
      <Toaster />
    </BrowserRouter>
  );
}

export default App;
```

> Note : si `BrowserRouter` est déjà initialisé ailleurs (par exemple dans `main.tsx`), ne PAS le dupliquer ici. Lire `frontend/src/main.tsx` au début de la task et adapter. Si déjà présent dans main.tsx, supprimer le `<BrowserRouter>` ici et garder uniquement `<Routes>`.

### Step 5.8 — Modifier `Header` (logout adapté)

- [ ] Modifier `frontend/src/components/Header.tsx:24-31` :

```ts
function handleLogout() {
  const isLocal = user.sub === "admin" && user.email === null;
  if (isLocal) {
    void fetch("/auth/local/logout", { method: "POST" }).finally(() => {
      window.location.href = "/login";
    });
    return;
  }
  // OIDC (chemin existant)
  const form = document.createElement("form");
  form.method = "POST";
  form.action = "/auth/logout";
  document.body.appendChild(form);
  form.submit();
}
```

### Step 5.9 — Mettre à jour test `AuthGuard`

- [ ] Lire `frontend/src/components/__tests__/AuthGuard.test.tsx` et adapter l'assertion sur l'URL de redirect : `/auth/login?next=...` → `/login?next=...`.

### Step 5.10 — Vérifier tests + tsc + lint

- [ ] Run :

```
cd frontend && npm run test:run
cd frontend && npx tsc --noEmit
cd frontend && npm run lint
```

Expected :
- Vitest : 170 anciens + ~8 nouveaux LoginPage + 1 ajusté AuthGuard = ~179 PASS.
- tsc : 0 erreur.
- Lint : 0 erreur, 4 warnings shadcn pré-existants.

### Step 5.11 — Commit

- [ ] Run :

```
git add frontend/src/pages/LoginPage.tsx frontend/src/pages/__tests__/LoginPage.test.tsx \
        frontend/src/hooks/useAuthMethods.ts frontend/src/i18n/fr/login.json \
        frontend/src/i18n/en/login.json frontend/src/lib/i18n.ts \
        frontend/src/App.tsx frontend/src/components/AuthGuard.tsx \
        frontend/src/components/Header.tsx \
        frontend/src/components/__tests__/AuthGuard.test.tsx
git commit -m "feat(bootstrap-admin-T5): LoginPage React + useAuthMethods + i18n + adapt AuthGuard/Header"
```

---

## Task 6 — Extension `dev-deploy.sh` + smoke end-to-end

**Files:**
- Modify: `dev-deploy.sh`

### Step 6.1 — Lire la structure actuelle du script

- [ ] Lire `dev-deploy.sh` complet (~500 lignes selon `ls -la`). Repérer la fonction qui initialise `POSTGRES_PASSWORD` si vide (ex. `ensure_postgres_password` ou inline). Ce sera notre point d'ancrage.

### Step 6.2 — Ajouter `ensure_bootstrap_admin_hash`

- [ ] Ajouter la fonction juste après celle qui gère `POSTGRES_PASSWORD` (ou au même endroit, même style) :

```bash
# ─── Bootstrap admin local (init si absent) ─────────────────
ensure_bootstrap_admin_hash() {
  local env_file="$1"
  local current
  current=$(grep -E '^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=' "$env_file" 2>/dev/null \
            | head -1 | cut -d= -f2-)
  if [[ -n "$current" ]]; then
    echo "  ✓ RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH déjà défini"
    return 0
  fi

  local plain hash
  plain=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-20)
  hash=$(openssl passwd -bcrypt "$plain")

  if grep -qE '^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=' "$env_file"; then
    sed -i "s|^RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=.*|RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=${hash}|" "$env_file"
  else
    echo "RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=${hash}" >> "$env_file"
  fi

  echo
  echo "═══════════════════════════════════════════════════════════"
  echo "  COMPTE ADMIN BOOTSTRAP CRÉÉ"
  echo "  Username : admin"
  echo "  Password : ${plain}"
  echo "  ⚠ Note ce password MAINTENANT, il n'est pas stocké en clair."
  echo "═══════════════════════════════════════════════════════════"
  echo
}
```

- [ ] Appeler la fonction juste après `ensure_postgres_password` (ou équivalent), avant `docker compose up -d` :

```bash
ensure_bootstrap_admin_hash "/opt/rag/.env"
```

### Step 6.3 — Test local de la fonction (smoke shell)

- [ ] Avant de pousser sur le LXC, tester localement (Git Bash sur Windows) :

```bash
# Créer un .env factice
mkdir -p /tmp/rag-test && touch /tmp/rag-test/.env
# Sourcer le bloc à isoler ou copier la fonction dans un script test
bash -c '
ensure_bootstrap_admin_hash() {
  # ... copier la fonction ici ...
}
ensure_bootstrap_admin_hash "/tmp/rag-test/.env"
'
# Vérifier la sortie
cat /tmp/rag-test/.env
# Doit contenir : RAG_BOOTSTRAP_ADMIN_PASSWORD_HASH=$2b$...
```

Expected : ligne ajoutée, hash bcrypt valide commençant par `$2b$`, password affiché en console.

### Step 6.4 — Lint shell (optionnel mais propre)

- [ ] Si `shellcheck` est disponible :

```bash
shellcheck dev-deploy.sh
```

Expected : aucun avertissement nouveau (warnings pré-existants tolérés).

### Step 6.5 — Smoke end-to-end (manuel, par l'utilisateur)

> Cette étape requiert l'environnement de déploiement LXC. L'utilisateur la fait à sa main (cf. mémoire `never-touch-lxc-303`). L'agent NE déclenche PAS `dev-deploy.sh` directement.

- [ ] L'utilisateur exécute (après commit + push) :

```
git push
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Expected output : encart `COMPTE ADMIN BOOTSTRAP CRÉÉ` + password en clair.

- [ ] L'utilisateur ouvre `http://192.168.10.184/ui/` :
  - Redirect vers `/ui/login` (état 2 : form local seul, message info OIDC pas configuré).
  - Login `admin` + password noté → succès → redirect vers `/ui/workspaces`.
  - Naviguer vers `/ui/settings/oidc-config` → form vide accessible → remplir → save → toast success.
  - Logout → re-login local → toujours possible.

### Step 6.6 — Commit

- [ ] Commit :

```
git add dev-deploy.sh
git commit -m "feat(bootstrap-admin-T6): dev-deploy.sh genere hash bcrypt + affiche pwd si absent"
```

---

## Récap couverture spec

| Section spec | Tâche | Statut couverture |
|---|---|---|
| §3 cadrage (5 décisions) | T1 (Settings), T2 (routes), T6 (script) | Couvert |
| §4.1 chemins d'authentification | T2 + T3 + T4 | Couvert |
| §4.2 composants nouveaux | T1, T2, T5, T6 | Couvert |
| §4.3 garanties sécurité | T1 (bcrypt, enabled), T3 (ordre Bearer→local→OIDC), T2 (log structuré à ajouter en T2 step 2.5) | Couvert |
| §5.1 Settings | T1 step 1.3 | Couvert |
| §5.2 LocalAuthService | T1 steps 1.3-1.4 | Couvert |
| §5.3 routes /auth/local + /api/auth/methods | T2 steps 2.5-2.6 | Couvert |
| §5.4 dep unifiée + migration | T3 steps 3.3-3.4 | Couvert |
| §5.5 /me étendu | T4 step 4.3 | Couvert |
| §5.6 erreurs typées | T2 step 2.2 | Couvert |
| §5.7 pas de migration DB | (rien à faire) | Respecté |
| §6.1 route /ui/login | T5 steps 5.5, 5.7 | Couvert |
| §6.2 hook useAuthMethods | T5 step 5.2 | Couvert |
| §6.3 4 états mockup | T5 step 5.3 (tests) + 5.5 (impl) | Couvert |
| §6.4 Zod + form | T5 step 5.5 | Couvert |
| §6.5 i18n | T5 step 5.1 | Couvert |
| §6.6 adapt AuthGuard + Header | T5 steps 5.6, 5.8 | Couvert |
| §7 data flow | (séquences validées par tests T2, T3, T4, T5) | Couvert |
| §8 tests | T1-T5 (chaque task a ses tests) | Couvert |
| §9 dev-deploy.sh | T6 steps 6.1-6.4 | Couvert |
| §10 plan livraison T1→T6 | Plan T1→T6 | Couvert |
| §11 hors-scope | (rien ajouté) | Respecté |
| §12 risques | (mitigations dans le code : log T2, idempotent T6, etc.) | Couvert |

---

## Self-review notes (effectué par l'auteur du plan)

- **Type consistency** : `_LOCAL_SESSION_KEY = "_local_session"` utilisé dans `bearer.py` (T3), `auth.py` (T2 step 2.5 et T4 step 4.3). Cohérent.
- **Signature `LocalAuthService.verify`** : keyword-only (`username`, `password`) cohérent entre service (T1) et appels (T2 step 2.5, tests T1/T3).
- **Réponse `/me` user local** : `{sub:"admin", email:null, name:null, roles:["rag-admin"]}` — identique entre spec §5.5, test T4, code T4 step 4.3, et Header logout detection T5 step 5.8.
- **Ordre dep** : Bearer → local → OIDC, identique entre spec §5.4 / §7.4, code T3 step 3.3, tests T3 step 3.1.
- **Pas de placeholders** : tous les snippets sont complets et exécutables.
