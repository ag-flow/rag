# M5a — OIDC Backend (Keycloak) : Spec de design

**Date** : 2026-05-16
**Branche** : `dev`
**Pré-requis** : M0 (Harpocrate vault), M2 (admin master-key, `oidc_config` table créée vide).

## 1. Objectif

Premier sous-jalon de M5 (IHM web). Pose la fondation d'authentification
OIDC contre Keycloak pour l'IHM future (M5b+). Backend-only — aucun
frontend dans ce jalon.

Le scope strict :
- CRUD config OIDC (master-key) : `POST /admin/oidc`, `GET /admin/oidc`.
- Flow OAuth2/OIDC : `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout`, `POST /auth/refresh`.
- Endpoint `GET /me` : retourne user info + roles.
- Dependency FastAPI `require_oidc_role(role)` réutilisable par M5b+.
- Wiring `SessionMiddleware` Starlette pour cookies signés.

Hors scope : SPA frontend, refresh middleware automatique (frontend appelle
`/auth/refresh` sur 401), multi-tenant (1 seule config OIDC), audit log
des login.

## 2. Architecture & data flow

```
[Setup admin]
admin → POST /admin/oidc {issuer, client_id, client_secret_ref}
        (Bearer master-key) → store dans oidc_config (1 row max)

[Login flow]
Browser → GET /auth/login?next=/ui/workspaces
              │
              ▼
      OidcService.discover() (lazy + cache 1h)
        - SELECT oidc_config (503 si vide)
        - Resolve client_secret via Harpocrate (${vault://rag:keycloak_secret})
        - GET ${issuer}/.well-known/openid-configuration → cache
        - GET ${jwks_uri} → cache
              │
              ▼
      Génère state + nonce
      Stocke (state, nonce, next) dans cookie signé "_oidc_state"
      (TTL 5 min, HttpOnly, Secure, SameSite=Lax)
              │
              ▼
      302 Redirect → ${authorization_endpoint}?
                       client_id=...&redirect_uri=${PUBLIC_URL}/auth/callback
                       &response_type=code&scope=openid+email+profile
                       &state=...&nonce=...

Browser → Keycloak login UI → user s'authentifie

Browser → GET /auth/callback?code=xxx&state=yyy
              │
              ▼
      Verify cookie "_oidc_state".state == query.state (CSRF)
              │
              ▼
      OidcService.exchange_code(code, expected_nonce=cookie.nonce)
        - POST ${token_endpoint} avec code + client_secret
        - Receive id_token + access_token + refresh_token
        - Verify id_token signature (JWKS) + claims (iss, aud, exp, nonce)
              │
              ▼
      Set cookie "_oidc_session" (signé, HttpOnly, Secure, SameSite=Lax)
        contenu : {id_token, refresh_token, exp}
      Delete cookie "_oidc_state"
              │
              ▼
      302 Redirect → cookie.next (validé : path relatif `/...` only)

[Subsequent requests via dependency]
Browser → GET /me  (cookie envoyé automatiquement)
              │
              ▼
      Depends(require_oidc_role("rag-viewer"))
        - Read cookie "_oidc_session" → 401 si absent ou altéré
        - Verify id_token signature + iss/aud/exp
            - Si TokenExpired → frontend appelle POST /auth/refresh
        - Extract roles = claims.resource_access[client_id].roles
        - role match ou hierarchy (admin > viewer) → OK, sinon 403
        - Returns OidcUserContext(sub, email, name, roles)

[Refresh transparent (endpoint dédié, appelé par frontend)]
Browser → POST /auth/refresh (cookie envoyé)
              │
              ▼
      OidcService.refresh(cookie.refresh_token)
        - POST ${token_endpoint} grant_type=refresh_token
        - Set new "_oidc_session" cookie (nouveau id_token + refresh_token + exp)
        - 200 {ok: true}
      Sur échec → 401 oidc_session_expired → frontend redirect /auth/login

[Logout]
Browser → POST /auth/logout
              │
              ▼
      Delete cookie "_oidc_session"
      302 Redirect → ${end_session_endpoint}?
                       id_token_hint=...&post_logout_redirect_uri=${PUBLIC_URL}/
              │
              ▼
      Keycloak invalide la session côté serveur
      Redirect navigateur → /
```

## 3. Décisions de design

| Sujet | Choix | Pourquoi |
|---|---|---|
| **Library OIDC Python** | `authlib` | Standard OAuth2/OIDC Python, support discovery + JWKS auto, bien maintenu. |
| **Session storage** | Cookie signé contenant id_token JWT + refresh_token | Stateless. Pas de table session DB. Multi-instance OK out-of-the-box. |
| **Refresh strategy** | Endpoint dédié `POST /auth/refresh` appelé par le frontend sur 401 | Plus simple que middleware response-wrapper. Frontend gère le retry. |
| **Rôles extraction** | `claims.resource_access.<client_id>.roles` | Standard Keycloak, pas de config spéciale (vs custom claim mapper). |
| **Discovery** | Lazy au premier login, cache 1h | Évite de planter le boot si Keycloak indisponible. Performance OK (1 fetch / h). |
| **JWKS cache** | 1h TTL + reload-on-verify-fail | Standard pour gérer rotation des clés Keycloak. |
| **Logout** | Redirect Keycloak `end_session_endpoint` | Logout propre des 2 côtés (sinon session Keycloak active = login auto au refresh). |
| **Hierarchy rôles** | `rag-admin` grants `rag-viewer` | Convention : un admin a tous les droits d'un viewer. |
| **Boot sans config** | 503 `oidc_not_configured` sur `/auth/*` et `/me`, master-key endpoints OK | OIDC est une couche optionnelle ajoutée pour l'IHM. Service marche sans. |
| **Cookie signature** | `SessionMiddleware` Starlette + `RAG_SESSION_SECRET` (32+ bytes) | Standard Starlette. Si env absent → fallback `RAG_MASTER_KEY` (dev only, warning). |
| **CSRF protection** | state + nonce | OAuth2 standard. State validé via cookie éphémère "_oidc_state". |
| **Open redirect protection** | Whitelist `next` : path relatif `/...` only | Reject absolute URLs (`http://attacker.com`). |

## 4. Composants

### 4.1 Nouveaux modules

| Fichier | Rôle | LOC cible |
|---|---|---|
| `backend/src/rag/services/oidc.py` | `OidcService` : CRUD config, discovery + JWKS cache, exchange_code, refresh, verify_id_token, build URLs | ~250 |
| `backend/src/rag/api/admin_oidc.py` | Router master-key : `POST /admin/oidc`, `GET /admin/oidc` | ~50 |
| `backend/src/rag/api/auth.py` | Router IHM : `/auth/login`, `/auth/callback`, `/auth/logout`, `/auth/refresh`, `/me` | ~150 |
| `backend/src/rag/auth/oidc_dependency.py` | `require_oidc_role(role)` factory + `_role_grants` hierarchy + cookie helpers | ~100 |
| `backend/src/rag/schemas/oidc.py` | `OidcConfigCreate`, `OidcConfigRead`, `MeResponse`, `OidcUserContext` (dataclass) | ~50 |

### 4.2 Modifications de modules existants

- `backend/src/rag/main.py` :
  - Import `OidcService`, `build_admin_oidc_router`, `build_auth_router`, `SessionMiddleware`.
  - Lifespan : instancier `OidcService` → `app.state.oidc`.
  - `app.add_middleware(SessionMiddleware, secret_key=settings.rag_session_secret.get_secret_value(), same_site="lax", https_only=...)`.
  - `app.include_router(build_admin_oidc_router())` + `app.include_router(build_auth_router())`.

- `backend/src/rag/config.py` :
  - Ajouter `rag_session_secret: SecretStr` avec fallback `rag_master_key` via `model_validator`.
  - Validator longueur ≥ 32 bytes.

- `backend/src/rag/api/errors.py` :
  - Ajouter `OidcNotConfigured` (503), `OidcKeycloakUnreachable` (503), `OidcStateMissing` (400), `OidcStateMismatch` (400), `OidcInvalidCode` (400), `OidcSessionMissing` (401), `OidcInvalidSession` (401), `OidcSessionExpired` (401), `OidcRoleForbidden` (403), `OidcInvalidToken` (401).

- `backend/pyproject.toml` :
  - Ajouter `authlib>=1.3` aux dépendances.

## 5. OidcService — détail

```python
@dataclass(frozen=True)
class OidcConfig:
    issuer: str
    client_id: str
    client_secret_ref: str


@dataclass(frozen=True)
class _DiscoveryDoc:
    authorization_endpoint: str
    token_endpoint: str
    end_session_endpoint: str
    jwks_uri: str
    fetched_at: float  # time.monotonic()


@dataclass(frozen=True)
class _TokenPair:
    id_token: str
    access_token: str
    refresh_token: str
    expires_at: int  # epoch seconds


@dataclass(frozen=True)
class OidcUserContext:
    sub: str
    email: str | None
    name: str | None
    roles: list[str]


class OidcService:
    _DISCOVERY_TTL_SECONDS = 3600

    def __init__(
        self,
        *,
        config_pool: asyncpg.Pool,
        secret_resolver: _ResolverProtocol,
        public_url: str,
        http_client: httpx.AsyncClient | None = None,
    ) -> None: ...

    # --- CRUD ---
    async def get_config(self) -> OidcConfig | None: ...
    async def upsert_config(self, *, issuer: str, client_id: str, client_secret_ref: str) -> OidcConfig: ...

    # --- Discovery + JWKS ---
    async def _discover(self, config: OidcConfig) -> _DiscoveryDoc: ...
    async def _jwks(self, discovery: _DiscoveryDoc) -> JsonWebKeySet: ...

    # --- OAuth2 flow ---
    async def build_authorize_url(self) -> tuple[str, str, str]:
        """Return (url, state, nonce). Caller stocke state+nonce dans cookie."""

    async def exchange_code(self, *, code: str, expected_nonce: str) -> _TokenPair: ...
    async def refresh(self, refresh_token: str) -> _TokenPair: ...

    # --- Verify ---
    async def verify_id_token(self, id_token: str) -> dict[str, Any]:
        """Verify signature (JWKS), iss, aud, exp.
        Raise OidcInvalidToken / OidcTokenExpired."""

    def extract_roles(self, claims: dict[str, Any], client_id: str) -> list[str]: ...

    def build_logout_url(self, id_token: str) -> str: ...
```

### Réutilisation des composants existants

- `SecretResolver` (M0) : résout `client_secret_ref` → secret via Harpocrate.
- Pattern `_ResolverProtocol` : déjà utilisé en M3/M4a/M4b/M4c.
- Pattern `dataclass(frozen=True)` : cohérent avec `McpWorkspaceRef`, `_CacheEntry`.

## 6. Endpoints

### `POST /admin/oidc` (master-key)

```json
Request : {
  "issuer": "https://keycloak.yoops.org/realms/homelab",
  "client_id": "rag-service",
  "client_secret_ref": "keycloak_rag_client_secret"
}
Response 201 : {
  "issuer": "...",
  "client_id": "rag-service",
  "client_secret_ref": "keycloak_rag_client_secret"
}
```

Upsert : si une config existe déjà, elle est remplacée. `client_secret_ref` est juste la clé logique (pas le secret) — résolu à l'usage via Harpocrate.

### `GET /admin/oidc` (master-key)

`200 OK` avec le payload ci-dessus, ou `503 oidc_not_configured`.

### `GET /auth/login?next=/ui/workspaces`

`302 Redirect` vers Keycloak authorize URL avec state + nonce + redirect_uri=${PUBLIC_URL}/auth/callback. Set cookie `_oidc_state` (signé, 5 min).

Validation `next` : path relatif (starts with `/`) only. Sinon → `/`.

### `GET /auth/callback?code=...&state=...`

- Verify cookie `_oidc_state`.state == query.state → 400 si mismatch.
- Exchange code → tokens.
- Set cookie `_oidc_session`. Delete cookie `_oidc_state`.
- `302 Redirect` vers `cookie.next`.

### `POST /auth/refresh`

- Read cookie `_oidc_session.refresh_token`.
- POST Keycloak `token_endpoint` grant_type=refresh_token.
- Si OK : set new `_oidc_session` cookie, `200 {ok: true}`.
- Si refresh rejeté : `401 oidc_session_expired`.

### `POST /auth/logout`

- Delete cookie `_oidc_session`.
- `302 Redirect` vers `${end_session_endpoint}?id_token_hint=...&post_logout_redirect_uri=${PUBLIC_URL}/`.

### `GET /me` (Depends require_oidc_role("rag-viewer"))

```json
Response 200 : {
  "sub": "user-uuid-from-keycloak",
  "email": "user@yoops.org",
  "name": "Black Beard",
  "roles": ["rag-admin"]
}
```

## 7. Dependency `require_oidc_role`

```python
def require_oidc_role(role: str) -> Callable[..., Awaitable[OidcUserContext]]:
    """Factory de dependency FastAPI.

    Hierarchy : `rag-admin` grants `rag-viewer`.
    """
    async def _dep(request: Request) -> OidcUserContext:
        oidc = request.app.state.oidc
        cookie = request.cookies.get("_oidc_session")
        if not cookie:
            raise OidcSessionMissing()  # 401

        session = _verify_session_cookie(cookie)  # 401 si signature KO
        try:
            claims = await oidc.verify_id_token(session["id_token"])
        except OidcTokenExpired as e:
            # Pas de refresh automatique ici : frontend doit POST /auth/refresh
            raise OidcSessionExpired() from e

        cfg = await oidc.get_config()
        if cfg is None:
            raise OidcNotConfigured()

        roles = oidc.extract_roles(claims, cfg.client_id)
        if not _role_grants(role, user_roles=roles):
            raise OidcRoleForbidden(required=role, has=roles)  # 403

        return OidcUserContext(
            sub=claims["sub"],
            email=claims.get("email"),
            name=claims.get("name"),
            roles=roles,
        )
    return _dep


def _role_grants(required: str, *, user_roles: list[str]) -> bool:
    if required in user_roles:
        return True
    if required == "rag-viewer" and "rag-admin" in user_roles:
        return True
    return False
```

## 8. Schemas

```python
# schemas/oidc.py
class OidcConfigCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    issuer: HttpUrl
    client_id: str = Field(..., min_length=1, max_length=255)
    client_secret_ref: str = Field(..., min_length=1, max_length=255)


class OidcConfigRead(BaseModel):
    issuer: str
    client_id: str
    client_secret_ref: str


class MeResponse(BaseModel):
    sub: str
    email: str | None
    name: str | None
    roles: list[str]
```

## 9. Matrice d'erreurs

| Code | Détail | Source | Quand |
|---|---|---|---|
| **201** | `OidcConfigRead` | `POST /admin/oidc` | upsert OK |
| **200** | `OidcConfigRead` | `GET /admin/oidc` | config OK |
| **302** | Location | `/auth/login` `/auth/callback` `/auth/logout` | succès |
| **200** | `{ok: true}` | `POST /auth/refresh` | refresh OK |
| **200** | `MeResponse` | `GET /me` | session OK |
| **400** | `oidc_state_missing` | `/auth/callback` | cookie `_oidc_state` absent |
| **400** | `oidc_state_mismatch` | `/auth/callback` | query.state != cookie.state |
| **400** | `oidc_invalid_code` | `/auth/callback` | Keycloak refuse le code |
| **401** | `oidc_session_missing` | dependency | pas de cookie `_oidc_session` |
| **401** | `oidc_invalid_session` | dependency | signature cookie KO |
| **401** | `oidc_session_expired` | dependency / `/auth/refresh` | id_token expiré OU refresh_token rejeté |
| **401** | `oidc_invalid_token` | dependency | JWT signature ou claim invalide |
| **403** | `oidc_role_forbidden` + `required` + `has` | dependency | role insuffisant |
| **422** | _(Pydantic)_ | `POST /admin/oidc` | body invalide |
| **503** | `oidc_not_configured` | OidcService / dependency / `/auth/*` | aucune config en DB |
| **503** | `oidc_keycloak_unreachable` | discovery fetch | Keycloak HS / timeout |
| **502** | `vault_unreachable` (M2 existing) | resolve client_secret | Harpocrate HS |

## 10. Tests

### Unit (sans DB, sans Keycloak)

- `tests/unit/services/test_oidc_config_service.py` :
  - `get_config()` retourne None si vide
  - `upsert_config()` INSERT puis UPDATE (1 row max)

- `tests/unit/services/test_oidc_discovery.py` :
  - discovery fetch via httpx MockTransport — parse les 4 endpoints
  - cache TTL : 2e appel dans la fenêtre 1h ne re-fetch pas
  - reload après TTL
  - `OidcKeycloakUnreachable` si HTTP timeout

- `tests/unit/services/test_oidc_verify.py` :
  - id_token signé par JWKS mock → OK
  - signature altérée → `OidcInvalidToken`
  - exp passé → `OidcTokenExpired`
  - iss/aud incorrect → `OidcInvalidToken`

- `tests/unit/services/test_oidc_exchange.py` :
  - exchange_code happy path (httpx mock token_endpoint)
  - nonce mismatch → `OidcInvalidToken`
  - refresh happy path
  - refresh rejeté (400 Keycloak) → `OidcSessionExpired`

- `tests/unit/services/test_oidc_roles.py` :
  - `extract_roles({"resource_access": {"rag-service": {"roles": ["rag-admin"]}}}, "rag-service")` → `["rag-admin"]`
  - claims sans resource_access → `[]`
  - claims sans le client_id ciblé → `[]`

- `tests/unit/auth/test_oidc_dependency.py` :
  - cookie absent → 401 missing
  - cookie altéré → 401 invalid
  - id_token expiré → 401 expired
  - role match exact → OK
  - role admin → viewer endpoint OK (hierarchy)
  - role viewer → admin endpoint → 403

- `tests/unit/schemas/test_oidc_dto.py` :
  - `OidcConfigCreate` accept valid, reject issuer non-URL, reject client_id empty, reject extra fields.

### Integration (DB jetable + Keycloak mocké via httpx)

- `tests/api/test_admin_oidc.py` : POST + GET avec master-key. 401 sans master key. Upsert behavior.

- `tests/api/test_auth_flow.py` :
  - injecter un `OidcService` avec un `httpx.AsyncClient(transport=MockTransport)` qui simule Keycloak (discovery, JWKS, token_endpoint).
  - GET /auth/login → 302 vers fake authorize URL, cookie `_oidc_state` set.
  - GET /auth/callback?code=X&state=cookieState → cookie `_oidc_session` set, 302 vers `next`.
  - GET /me → 200 user payload.
  - POST /auth/refresh → new cookie, 200.
  - POST /auth/logout → cookie cleared, 302 vers fake logout URL.

- `tests/api/test_auth_errors.py` :
  - 503 sans config
  - 400 state mismatch
  - 400 oidc_invalid_code
  - 401 cookie absent sur /me
  - 401 cookie altéré
  - 403 role insuffisant (viewer essaie /admin)

### Smoke opt-in (`@pytest.mark.smoke`)

- `tests/api/test_auth_e2e_keycloak_smoke.py` :
  - Skip si pas de `KEYCLOAK_TEST_ISSUER` / `KEYCLOAK_TEST_CLIENT_ID` / `KEYCLOAK_TEST_USER` / `KEYCLOAK_TEST_PASSWORD` / `HARPOCRATE_TEST_CLIENT_SECRET_REF`.
  - Driving le login HTML Keycloak via httpx + parsing form pour POST credentials.
  - Si trop fragile : ce smoke est reporté à M5b avec Playwright (qui drive un vrai navigateur).

### Couverture cible

| Module | Cible |
|---|---|
| `services/oidc.py` | ≥ 90% |
| `api/admin_oidc.py` | 100% (via integration) |
| `api/auth.py` | ≥ 95% |
| `auth/oidc_dependency.py` | 100% |
| `schemas/oidc.py` | 100% |

## 11. Wiring `main.py`

```python
# Imports en haut du fichier
from rag.api.admin_oidc import build_admin_oidc_router
from rag.api.auth import build_auth_router
from rag.services.oidc import OidcService
from starlette.middleware.sessions import SessionMiddleware

# Dans build_app lifespan, après registry.start() + migrations + resolver :
app.state.oidc = OidcService(
    config_pool=registry.config_pool,
    secret_resolver=app.state.resolver,
    public_url=str(settings.rag_public_url).rstrip("/"),
)

# Middleware (avant les routers) :
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.rag_session_secret.get_secret_value(),
    same_site="lax",
    https_only=(settings.environment != "dev"),
)

# Include routers (après les existants) :
app.include_router(build_admin_oidc_router())
app.include_router(build_auth_router())
```

## 12. Modif `config.py`

Ajouter dans `Settings` :

```python
rag_session_secret: SecretStr = SecretStr("")  # fallback géré ci-dessous

@model_validator(mode="after")
def fill_session_secret_fallback(self) -> "Settings":
    if not self.rag_session_secret.get_secret_value():
        # Fallback dev : utilise rag_master_key. Warning loggé.
        self.rag_session_secret = self.rag_master_key
    if len(self.rag_session_secret.get_secret_value()) < 32:
        raise ValueError("RAG_SESSION_SECRET must be ≥ 32 chars (use `openssl rand -hex 32`)")
    return self
```

## 13. Modif `pyproject.toml`

Ajouter dans `[project] dependencies` :

```
"authlib>=1.3,<2.0",
```

`authlib` fournit `authlib.integrations.httpx_client.AsyncOAuth2Client` pour OAuth2 et `authlib.jose.JsonWebKey`/`jwt` pour JWT verify + JWKS.

## 14. Hors scope

- Frontend SPA (M5b)
- Refresh transparent via middleware response-wrapper (on a opté pour `/auth/refresh` côté frontend)
- Multi-tenant (1 seule config OIDC)
- Audit log des login (à voir M5c+)
- Group membership (les rôles suffisent)
- Token introspection (validation locale JWKS)
- Multi-instance session sync (cookie signé stateless → OK out-of-the-box)

## 15. Risques connus

| Risque | Mitigation |
|---|---|
| `RAG_SESSION_SECRET` faible → cookies forgeable | Validator config ≥ 32 chars. Doc : `openssl rand -hex 32`. |
| JWT replay si attaquant vole le cookie | HttpOnly + Secure + SameSite=Lax. Pas de défense parfaite sans session store. |
| JWKS rotation Keycloak invalidate cache | Reload JWKS once on signature fail + retry verify. |
| Open redirect via `?next=` | Whitelist : path relatif `/...` only, reject `http(s)://`. |
| State cookie expire pendant login | TTL 5 min. Si user > 5 min → 400 state_missing, recommencer. |
| Keycloak indispo au boot | Discovery lazy → boot OK, 503 sur `/auth/*` jusqu'au retour Keycloak. |
| Smoke Keycloak fragile (HTML parsing du login form) | Reporter à M5b avec Playwright si trop instable. |
