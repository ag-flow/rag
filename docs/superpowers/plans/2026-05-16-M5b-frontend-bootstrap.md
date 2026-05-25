# M5b — Frontend Bootstrap + Page Workspaces Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer un frontend complet (Vite + React 18 + TS strict + Tailwind + shadcn/ui + react-router + TanStack Query + i18next) avec une page Workspaces CRUD fonctionnelle, derrière OIDC (cookie session M5a) ou master-key (rétrocompat machines).

**Architecture:** Backend modifié pour qu'une seule dependency `require_master_key_or_oidc_role("rag-admin")` accepte les deux modes d'auth. Frontend bootstrap sur projet `frontend/` from scratch : Nginx alpine en prod (Dockerfile multi-stage), Vite dev server en local avec proxy `/api`+`/auth`+`/me` → backend LXC. Caddy reverse proxy `/ui*` → `frontend:80`. Layout shell light (sidebar D1 v2 + header user), une page Workspaces (table + create dialog + delete alert + dropdown actions + toast).

**Tech Stack:** React 18, TypeScript 5.6 strict, Vite 5, Tailwind 3, shadcn/ui, react-router-dom 6, @tanstack/react-query 5, i18next 23 + react-i18next 15, zod 3, react-hook-form 7, Vitest 2 + Testing Library 16, Nginx alpine, Docker multi-stage.

---

## File Structure

### Backend (modifs ciblées)

| Fichier | Statut |
|---|---|
| `backend/src/rag/auth/bearer.py` | **Modify** — ajouter `require_master_key_or_oidc_role(role)` factory |
| `backend/src/rag/api/admin.py` | **Modify** — remplacer `Depends(require_master_key)` par `Depends(require_master_key_or_oidc_role("rag-admin"))` |
| `backend/tests/api/test_admin_oidc_auth.py` | **Create** — 5 tests integration (master-key OK, OIDC admin OK, OIDC viewer 403, sans auth 401, admin_oidc reste master-key only) |

### Frontend (projet from scratch)

| Fichier | Statut |
|---|---|
| `frontend/package.json` | **Create** — deps complètes |
| `frontend/package-lock.json` | **Create** — généré par npm install |
| `frontend/tsconfig.json` | **Create** — strict mode |
| `frontend/tsconfig.node.json` | **Create** — pour vite.config.ts |
| `frontend/vite.config.ts` | **Create** — base /ui/, proxy /api+/auth+/me |
| `frontend/vitest.config.ts` | **Create** — jsdom + setup file |
| `frontend/tailwind.config.js` | **Create** — content paths + tokens D1 v2 |
| `frontend/postcss.config.js` | **Create** — autoprefixer + tailwind |
| `frontend/.eslintrc.cjs` | **Create** — TS + React hooks |
| `frontend/.prettierrc` | **Create** — config standard |
| `frontend/.gitignore` | **Create** — node_modules, dist, etc. |
| `frontend/index.html` | **Create** — root template |
| `frontend/Dockerfile` | **Create** — multi-stage node → nginx |
| `frontend/nginx.conf` | **Create** — try_files SPA fallback |
| `frontend/README.md` | **Create** — quickstart dev |
| `frontend/src/main.tsx` | **Create** — entry point |
| `frontend/src/App.tsx` | **Create** — layout shell |
| `frontend/src/routes.tsx` | **Create** — router config |
| `frontend/src/lib/api.ts` | **Create** — fetch wrapper + 401 handler |
| `frontend/src/lib/i18n.ts` | **Create** — i18next config |
| `frontend/src/lib/validators.ts` | **Create** — Zod schemas |
| `frontend/src/lib/utils.ts` | **Create** — cn helper (shadcn) |
| `frontend/src/hooks/useMe.ts` | **Create** — GET /me TanStack Query |
| `frontend/src/hooks/useWorkspaces.ts` | **Create** — 5 hooks CRUD |
| `frontend/src/hooks/useToast.ts` | **Create** — wrapper shadcn toast |
| `frontend/src/components/AuthGuard.tsx` | **Create** |
| `frontend/src/components/Sidebar.tsx` | **Create** — D1 v2 |
| `frontend/src/components/Header.tsx` | **Create** — user dropdown |
| `frontend/src/components/StatusIndicator.tsx` | **Create** — 🟢🟠🔴 |
| `frontend/src/components/LoadingSpinner.tsx` | **Create** |
| `frontend/src/components/ui/button.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/input.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/label.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/select.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/table.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/dialog.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/alert-dialog.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/dropdown-menu.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/form.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/toast.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/toaster.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/card.tsx` | **Create** — shadcn |
| `frontend/src/components/ui/badge.tsx` | **Create** — shadcn |
| `frontend/src/pages/WorkspacesPage.tsx` | **Create** |
| `frontend/src/pages/WorkspaceCreateDialog.tsx` | **Create** |
| `frontend/src/pages/WorkspaceDeleteAlert.tsx` | **Create** |
| `frontend/src/pages/WorkspaceActions.tsx` | **Create** |
| `frontend/src/pages/NotFound.tsx` | **Create** |
| `frontend/src/i18n/fr/common.json` | **Create** |
| `frontend/src/i18n/fr/auth.json` | **Create** |
| `frontend/src/i18n/fr/nav.json` | **Create** |
| `frontend/src/i18n/fr/workspaces.json` | **Create** |
| `frontend/src/i18n/en/*.json` | **Create** — miroirs fr/* |
| `frontend/src/styles/globals.css` | **Create** — Tailwind directives + variables shadcn |
| `frontend/tests/setup.ts` | **Create** — testing-library + jest-dom |
| `frontend/tests/lib/api.test.ts` | **Create** |
| `frontend/tests/lib/validators.test.ts` | **Create** |
| `frontend/tests/hooks/useMe.test.tsx` | **Create** |
| `frontend/tests/hooks/useWorkspaces.test.tsx` | **Create** |
| `frontend/tests/components/AuthGuard.test.tsx` | **Create** |
| `frontend/tests/components/StatusIndicator.test.tsx` | **Create** |
| `frontend/tests/pages/WorkspacesPage.test.tsx` | **Create** |
| `frontend/tests/pages/WorkspaceCreateDialog.test.tsx` | **Create** |

### Infra

| Fichier | Statut |
|---|---|
| `docker-compose-dev.yml` | **Modify** — ajouter service `frontend` |
| `Caddyfile` | **Modify** — `/ui*` reverse proxy + `/auth/*` + `/me` |

---

## Task 1 : Backend dependency `require_master_key_or_oidc_role`

**Files:**
- Modify: `backend/src/rag/auth/bearer.py`
- Modify: `backend/src/rag/api/admin.py:46`
- Create: `backend/tests/api/test_admin_oidc_auth.py`

- [ ] **Step 1 : Écrire les 5 tests integration**

```python
# backend/tests/api/test_admin_oidc_auth.py
from __future__ import annotations

import time

from fastapi.testclient import TestClient
from joserfc import jwt
from joserfc.jwk import RSAKey


_RSA_KEY = RSAKey.generate_key(key_size=2048, private=True)
_KID = "test-kid"
_ISSUER = "https://kc.example.com/realms/test"
_CLIENT_ID = "rag-service"


def _signed(claims: dict) -> str:
    return jwt.encode({"alg": "RS256", "kid": _KID, "typ": "JWT"}, claims, _RSA_KEY)


def _jwks() -> dict:
    pub = _RSA_KEY.as_dict(private=False)
    pub["kid"] = _KID; pub["alg"] = "RS256"; pub["use"] = "sig"
    return {"keys": [pub]}


def _discovery() -> dict:
    return {
        "issuer": _ISSUER,
        "authorization_endpoint": f"{_ISSUER}/auth",
        "token_endpoint": f"{_ISSUER}/token",
        "end_session_endpoint": f"{_ISSUER}/logout",
        "jwks_uri": f"{_ISSUER}/jwks",
    }


def _install_keycloak_mock(client: TestClient, *, roles: list[str]) -> None:
    """Setup OIDC config + mock Keycloak http_client + log in to get session cookie."""
    import httpx

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        if "well-known" in url:
            return httpx.Response(200, json=_discovery())
        if "/jwks" in url:
            return httpx.Response(200, json=_jwks())
        if url.endswith("/token"):
            now = int(time.time())
            claims = {
                "iss": _ISSUER, "aud": _CLIENT_ID, "sub": "u",
                "email": "test@example.com", "name": "Test",
                "exp": now + 300, "iat": now,
                "nonce": client.app.state._kc_nonce,  # type: ignore[attr-defined]
                "resource_access": {_CLIENT_ID: {"roles": roles}},
            }
            return httpx.Response(200, json={
                "id_token": _signed(claims),
                "access_token": "at", "refresh_token": "rt",
                "expires_in": 300,
            })
        return httpx.Response(404)

    client.app.state.oidc._http_client = httpx.AsyncClient(  # type: ignore[attr-defined]
        transport=httpx.MockTransport(handler)
    )
    client.app.state.oidc._discovery_cache.clear()  # type: ignore[attr-defined]
    client.app.state.oidc._jwks_cache.clear()  # type: ignore[attr-defined]


def _seed_and_login(
    client: TestClient,
    admin_headers: dict[str, str],
    *,
    roles: list[str],
) -> None:
    """Pose la config OIDC + simule un login complet pour avoir un cookie session."""
    # 1. Config OIDC via master-key
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
    # Le stub resolver doit connaitre cette ref
    client.app.state.resolver.known.add("kc_test_secret")  # type: ignore[attr-defined]

    _install_keycloak_mock(client, roles=roles)

    # 2. /auth/login pour capturer state+nonce
    from urllib.parse import parse_qs, urlparse
    login_r = client.get("/auth/login", follow_redirects=False)
    params = parse_qs(urlparse(login_r.headers["location"]).query)
    client.app.state._kc_nonce = params["nonce"][0]  # type: ignore[attr-defined]

    # 3. callback pour poser le cookie session
    cb = client.get(f"/auth/callback?code=x&state={params['state'][0]}", follow_redirects=False)
    assert cb.status_code == 302


def test_post_workspaces_with_master_key_still_works(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """Non-régression : Bearer master-key reste accepté."""
    r = admin_client.post(
        "/workspaces",
        headers=admin_headers,
        json={
            "name": "ws_mk",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201


def test_post_workspaces_with_oidc_admin_role_succeeds(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """OIDC rag-admin sans Bearer → 201."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-admin"])

    # POST sans Authorization → utilise le cookie OIDC
    r = admin_client.post(
        "/workspaces",
        json={
            "name": "ws_oidc",
            "indexer": {
                "provider": "openai",
                "model": "text-embedding-3-small",
                "api_key_ref": "openai_embedding_key",
            },
        },
    )
    assert r.status_code == 201, r.text


def test_post_workspaces_with_oidc_viewer_role_returns_403(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """OIDC rag-viewer sans Bearer → 403 oidc_role_forbidden."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-viewer"])

    r = admin_client.post(
        "/workspaces",
        json={
            "name": "ws_viewer",
            "indexer": {"provider": "openai", "model": "text-embedding-3-small", "api_key_ref": "openai_embedding_key"},
        },
    )
    assert r.status_code == 403
    assert r.json()["error"] == "oidc_role_forbidden"


def test_post_workspaces_without_auth_returns_401(
    admin_client: TestClient,
    cleanup_ws_dbs_api: None,
) -> None:
    """Sans Bearer ni cookie → 401 oidc_session_missing."""
    r = admin_client.post(
        "/workspaces",
        json={"name": "x", "indexer": {"provider": "x", "model": "x"}},
    )
    assert r.status_code == 401


def test_admin_oidc_endpoint_still_requires_master_key(
    admin_client: TestClient,
    admin_headers: dict[str, str],
    cleanup_ws_dbs_api: None,
) -> None:
    """`POST /admin/oidc` reste master-key only (anti-lockout)."""
    _seed_and_login(admin_client, admin_headers, roles=["rag-admin"])

    # Tentative avec cookie OIDC seulement (sans Bearer) → 401
    r = admin_client.post(
        "/admin/oidc",
        json={
            "issuer": "https://kc.other.com/realms/r",
            "client_id": "other",
            "client_secret_ref": "other",
        },
    )
    assert r.status_code == 401
```

- [ ] **Step 2 : Run tests to verify they fail**

```powershell
cd backend
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_admin_oidc_auth.py -v
```

Expected : `ImportError: cannot import name 'require_master_key_or_oidc_role'` (sur certains tests) OU 401 où on attend 201 (les 2 tests OIDC qui ne peuvent pas marcher tant que la dependency n'est pas modifiée).

- [ ] **Step 3 : Implémenter `require_master_key_or_oidc_role` dans `bearer.py`**

Append à `backend/src/rag/auth/bearer.py` :

```python
from collections.abc import Awaitable, Callable


def require_master_key_or_oidc_role(
    role: str,
) -> Callable[[Request], Awaitable[None]]:
    """Dependency : accepte EITHER Bearer master-key OR cookie OIDC role.

    Priorité au Bearer si présent (cas machine/cURL/agents). Sinon délègue
    à `require_oidc_role(role)` qui check cookie session.

    Retourne None dans tous les cas (le contexte user OIDC n'est pas
    propagé via cette dependency — utiliser `require_oidc_role` direct
    si besoin de l'identité du user).
    """
    # Import retardé pour éviter cycle (oidc_dependency dépend de
    # rag.api.errors qui dépend potentiellement de rag.auth).
    from rag.auth.oidc_dependency import require_oidc_role
    oidc_dep = require_oidc_role(role)

    async def _dep(request: Request) -> None:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            require_master_key(request)
            return None
        await oidc_dep(request)
        return None

    return _dep
```

- [ ] **Step 4 : Modifier `api/admin.py:46`**

Edit `backend/src/rag/api/admin.py` :

a) Ligne ~6 (imports) — changer :
```python
from rag.auth.bearer import require_master_key
```
en :
```python
from rag.auth.bearer import require_master_key_or_oidc_role
```

b) Ligne 46 — changer :
```python
        dependencies=[Depends(require_master_key)],
```
en :
```python
        dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
```

- [ ] **Step 5 : Run tests to verify they pass**

```powershell
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run pytest tests/api/test_admin_oidc_auth.py -v
```

Expected : `5 passed`.

- [ ] **Step 6 : Run full suite — vérifier non-régression sur les autres tests admin**

```powershell
uv run pytest tests/api/ --tb=no -q
```

Expected : aucune régression sur les tests M2/M3/M4/M5a. Ils utilisent tous Bearer master-key qui continue de fonctionner.

- [ ] **Step 7 : Lint/format/mypy**

```powershell
uv run ruff check src/rag/auth/bearer.py src/rag/api/admin.py tests/api/test_admin_oidc_auth.py
uv run ruff format src/rag/auth/bearer.py src/rag/api/admin.py tests/api/test_admin_oidc_auth.py
uv run mypy src/rag/auth/bearer.py src/rag/api/admin.py
```

- [ ] **Step 8 : Commit**

```powershell
git add backend/src/rag/auth/bearer.py backend/src/rag/api/admin.py backend/tests/api/test_admin_oidc_auth.py
git commit -m "feat(M5b): require_master_key_or_oidc_role pour les CRUD admin via IHM"
```

---

## Task 2 : Bootstrap projet `frontend/` (package.json, tsconfig, vite, index.html)

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/tsconfig.json`
- Create: `frontend/tsconfig.node.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/index.html`
- Create: `frontend/.gitignore`
- Create: `frontend/README.md`

- [ ] **Step 1 : Créer `package.json`**

```json
{
  "name": "rag-frontend",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest",
    "test:run": "vitest run",
    "lint": "eslint . --ext ts,tsx",
    "format": "prettier --write \"src/**/*.{ts,tsx,css,json}\"",
    "typecheck": "tsc --noEmit"
  },
  "dependencies": {
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "react-router-dom": "^6.27.0",
    "@tanstack/react-query": "^5.59.16",
    "i18next": "^23.16.4",
    "react-i18next": "^15.1.0",
    "i18next-browser-languagedetector": "^8.0.0",
    "zod": "^3.23.8",
    "react-hook-form": "^7.53.1",
    "@hookform/resolvers": "^3.9.0",
    "clsx": "^2.1.1",
    "tailwind-merge": "^2.5.4",
    "class-variance-authority": "^0.7.0",
    "lucide-react": "^0.453.0",
    "@radix-ui/react-dialog": "^1.1.2",
    "@radix-ui/react-alert-dialog": "^1.1.2",
    "@radix-ui/react-dropdown-menu": "^2.1.2",
    "@radix-ui/react-label": "^2.1.0",
    "@radix-ui/react-select": "^2.1.2",
    "@radix-ui/react-slot": "^1.1.0",
    "@radix-ui/react-toast": "^1.2.2"
  },
  "devDependencies": {
    "@types/react": "^18.3.12",
    "@types/react-dom": "^18.3.1",
    "typescript": "^5.6.3",
    "vite": "^5.4.10",
    "@vitejs/plugin-react": "^4.3.3",
    "tailwindcss": "^3.4.14",
    "postcss": "^8.4.47",
    "autoprefixer": "^10.4.20",
    "vitest": "^2.1.4",
    "jsdom": "^25.0.1",
    "@testing-library/react": "^16.0.1",
    "@testing-library/user-event": "^14.5.2",
    "@testing-library/jest-dom": "^6.6.3",
    "eslint": "^9.13.0",
    "@typescript-eslint/eslint-plugin": "^8.12.2",
    "@typescript-eslint/parser": "^8.12.2",
    "eslint-plugin-react-hooks": "^5.0.0",
    "eslint-plugin-react-refresh": "^0.4.14",
    "prettier": "^3.3.3"
  }
}
```

- [ ] **Step 2 : Créer `tsconfig.json`**

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "Bundler",
    "allowImportingTsExtensions": false,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "esModuleInterop": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "baseUrl": ".",
    "paths": {
      "@/*": ["./src/*"]
    },
    "types": ["vitest/globals", "@testing-library/jest-dom"]
  },
  "include": ["src", "tests"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

- [ ] **Step 3 : Créer `tsconfig.node.json`**

```json
{
  "compilerOptions": {
    "composite": true,
    "skipLibCheck": true,
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "allowSyntheticDefaultImports": true,
    "strict": true
  },
  "include": ["vite.config.ts", "vitest.config.ts"]
}
```

- [ ] **Step 4 : Créer `vite.config.ts`**

```ts
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

const BACKEND = process.env.VITE_BACKEND_URL ?? "http://192.168.10.184:8000";

export default defineConfig({
  base: "/ui/",
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  server: {
    port: 5173,
    proxy: {
      "/api":  { target: BACKEND, changeOrigin: true },
      "/auth": { target: BACKEND, changeOrigin: true },
      "/me":   { target: BACKEND, changeOrigin: true },
    },
  },
  build: {
    outDir: "dist",
    sourcemap: true,
  },
});
```

- [ ] **Step 5 : Créer `index.html`**

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>ag-flow.rag</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

- [ ] **Step 6 : Créer `.gitignore`**

```
node_modules/
dist/
.env
.env.local
*.log
.vite/
coverage/
```

- [ ] **Step 7 : Créer `README.md`**

```markdown
# rag-frontend

IHM web pour ag-flow.rag (M5b — page Workspaces).

## Quickstart dev

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173/ui (proxy /api+/auth+/me → backend LXC 303)
```

Env var optionnelle :
```bash
VITE_BACKEND_URL=http://localhost:8000 npm run dev
```

## Commandes

- `npm run dev` — Vite dev server avec hot reload
- `npm run build` — build prod dans `dist/`
- `npm run test` — Vitest watch mode
- `npm run test:run` — Vitest run once
- `npm run lint` — ESLint
- `npm run format` — Prettier
- `npm run typecheck` — TypeScript check sans emit

## Build prod

Le `Dockerfile` multi-stage build avec node 20 puis serve via Nginx alpine.
```

- [ ] **Step 8 : Installer les deps**

```powershell
cd frontend
npm install
```

Expected : tous les packages installés, `package-lock.json` créé. Pas d'erreurs CRITICAL (warnings deprecation OK).

- [ ] **Step 9 : Vérifier le build initial (sans src/main.tsx encore)**

Ne pas lancer `npm run build` à ce stade (échouera car `src/main.tsx` absent). On va créer le source minimal dans la suite.

- [ ] **Step 10 : Commit**

```powershell
git add frontend/
git commit -m "feat(M5b): bootstrap frontend (Vite + React + TS strict + deps complètes)"
```

---

## Task 3 : Tooling — ESLint, Prettier, Vitest config

**Files:**
- Create: `frontend/.eslintrc.cjs`
- Create: `frontend/.prettierrc`
- Create: `frontend/vitest.config.ts`
- Create: `frontend/tests/setup.ts`

- [ ] **Step 1 : Créer `.eslintrc.cjs`**

```js
module.exports = {
  root: true,
  env: { browser: true, es2022: true, node: true },
  extends: [
    "eslint:recommended",
    "plugin:@typescript-eslint/recommended",
    "plugin:react-hooks/recommended",
  ],
  ignorePatterns: ["dist", ".eslintrc.cjs", "vite.config.ts", "vitest.config.ts"],
  parser: "@typescript-eslint/parser",
  plugins: ["react-refresh"],
  rules: {
    "react-refresh/only-export-components": ["warn", { allowConstantExport: true }],
    "@typescript-eslint/no-unused-vars": ["error", { argsIgnorePattern: "^_" }],
  },
};
```

- [ ] **Step 2 : Créer `.prettierrc`**

```json
{
  "semi": true,
  "trailingComma": "all",
  "singleQuote": false,
  "printWidth": 100,
  "tabWidth": 2,
  "useTabs": false
}
```

- [ ] **Step 3 : Créer `vitest.config.ts`**

```ts
import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: { "@": path.resolve(__dirname, "./src") },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html"],
      include: ["src/**/*.{ts,tsx}"],
      exclude: ["src/main.tsx", "src/components/ui/**", "**/*.d.ts"],
    },
  },
});
```

- [ ] **Step 4 : Créer `tests/setup.ts`**

```ts
import "@testing-library/jest-dom";
import { afterEach } from "vitest";
import { cleanup } from "@testing-library/react";

// Cleanup React DOM after each test (jsdom)
afterEach(() => {
  cleanup();
});
```

- [ ] **Step 5 : Vérifier que `npm run lint` ne crashe pas**

```powershell
npm run lint
```

Expected : "Oops! Something went wrong" → normal (pas de fichier src/ encore). Sinon, message "No files matching the pattern" → OK aussi.

- [ ] **Step 6 : Commit**

```powershell
git add frontend/.eslintrc.cjs frontend/.prettierrc frontend/vitest.config.ts frontend/tests/setup.ts
git commit -m "feat(M5b): tooling frontend (ESLint, Prettier, Vitest config)"
```

---

## Task 4 : Tailwind + tokens design D1 v2 + globals.css

**Files:**
- Create: `frontend/tailwind.config.js`
- Create: `frontend/postcss.config.js`
- Create: `frontend/src/styles/globals.css`
- Create: `frontend/src/lib/utils.ts`

- [ ] **Step 1 : Créer `tailwind.config.js`**

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))",
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))",
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))",
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))",
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))",
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))",
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))",
        },
      },
      borderRadius: {
        lg: "var(--radius)",
        md: "calc(var(--radius) - 2px)",
        sm: "calc(var(--radius) - 4px)",
      },
    },
  },
  plugins: [],
};
```

- [ ] **Step 2 : Créer `postcss.config.js`**

```js
export default {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
};
```

- [ ] **Step 3 : Créer `src/styles/globals.css` avec tokens D1 v2**

```css
@tailwind base;
@tailwind components;
@tailwind utilities;

@layer base {
  :root {
    /* Tokens shadcn standards adaptés au style D1 v2 */
    --background: 0 0% 100%;                  /* white */
    --foreground: 222.2 47.4% 11.2%;          /* slate-900 */

    --card: 0 0% 100%;
    --card-foreground: 222.2 47.4% 11.2%;

    --popover: 0 0% 100%;
    --popover-foreground: 222.2 47.4% 11.2%;

    --primary: 199 89% 39%;                   /* sky-600 #0284c7 (active sidebar) */
    --primary-foreground: 0 0% 100%;

    --secondary: 210 40% 96.1%;               /* slate-100 */
    --secondary-foreground: 222.2 47.4% 11.2%;

    --muted: 210 40% 96.1%;                   /* slate-100 */
    --muted-foreground: 215.4 16.3% 46.9%;    /* slate-500 */

    --accent: 210 40% 96.1%;
    --accent-foreground: 222.2 47.4% 11.2%;

    --destructive: 0 84.2% 60.2%;             /* red-500 */
    --destructive-foreground: 0 0% 100%;

    --border: 214.3 31.8% 91.4%;              /* slate-200 */
    --input: 214.3 31.8% 91.4%;
    --ring: 199 89% 39%;                      /* sky-600 (primary) */

    --radius: 0.5rem;
  }

  body {
    @apply bg-background text-foreground;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  }
}
```

- [ ] **Step 4 : Créer `src/lib/utils.ts` (helper `cn`)**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 5 : Commit**

```powershell
git add frontend/tailwind.config.js frontend/postcss.config.js frontend/src/styles/globals.css frontend/src/lib/utils.ts
git commit -m "feat(M5b): Tailwind + tokens shadcn (D1 v2) + cn helper"
```

---

## Task 5 : i18next setup + namespaces fr/en

**Files:**
- Create: `frontend/src/lib/i18n.ts`
- Create: `frontend/src/i18n/fr/common.json`
- Create: `frontend/src/i18n/fr/auth.json`
- Create: `frontend/src/i18n/fr/nav.json`
- Create: `frontend/src/i18n/fr/workspaces.json`
- Create: `frontend/src/i18n/en/common.json`
- Create: `frontend/src/i18n/en/auth.json`
- Create: `frontend/src/i18n/en/nav.json`
- Create: `frontend/src/i18n/en/workspaces.json`

- [ ] **Step 1 : Créer `src/lib/i18n.ts`**

```ts
import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import frCommon from "@/i18n/fr/common.json";
import frAuth from "@/i18n/fr/auth.json";
import frNav from "@/i18n/fr/nav.json";
import frWorkspaces from "@/i18n/fr/workspaces.json";

import enCommon from "@/i18n/en/common.json";
import enAuth from "@/i18n/en/auth.json";
import enNav from "@/i18n/en/nav.json";
import enWorkspaces from "@/i18n/en/workspaces.json";

void i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    fallbackLng: "fr",
    supportedLngs: ["fr", "en"],
    ns: ["common", "auth", "nav", "workspaces"],
    defaultNS: "common",
    resources: {
      fr: {
        common: frCommon,
        auth: frAuth,
        nav: frNav,
        workspaces: frWorkspaces,
      },
      en: {
        common: enCommon,
        auth: enAuth,
        nav: enNav,
        workspaces: enWorkspaces,
      },
    },
    interpolation: { escapeValue: false },
  });

export default i18n;
```

- [ ] **Step 2 : Créer les 4 fichiers fr/**

`frontend/src/i18n/fr/common.json` :
```json
{
  "buttons": {
    "cancel": "Annuler",
    "save": "Enregistrer",
    "create": "Créer",
    "delete": "Supprimer",
    "confirm": "Confirmer"
  },
  "loading": "Chargement…",
  "errors": {
    "generic": "Une erreur est survenue, réessayez.",
    "network": "Problème de connexion",
    "forbidden": "Permissions insuffisantes — contactez un admin."
  }
}
```

`frontend/src/i18n/fr/auth.json` :
```json
{
  "logout": "Déconnexion",
  "session_expired": "Session expirée — reconnexion nécessaire.",
  "not_configured": "OIDC n'est pas configuré. L'admin doit faire POST /admin/oidc."
}
```

`frontend/src/i18n/fr/nav.json` :
```json
{
  "sections": {
    "administration": "Administration",
    "usage": "Usage"
  },
  "items": {
    "workspaces": "Workspaces",
    "sources": "Sources",
    "jobs": "Jobs",
    "models": "Modèles",
    "push": "Push activity",
    "mcp": "Recherche MCP"
  }
}
```

`frontend/src/i18n/fr/workspaces.json` :
```json
{
  "title": "Workspaces",
  "create": "Créer un workspace",
  "empty": {
    "title": "Aucun workspace",
    "description": "Créez votre premier workspace pour commencer à indexer du contenu via git ou via push synchrone."
  },
  "table": {
    "name": "Nom",
    "indexer": "Indexer",
    "sources": "Sources",
    "documents": "Documents",
    "last_indexed": "Dernière indexation",
    "actions": "Actions",
    "never": "Jamais"
  },
  "form": {
    "name": "Nom",
    "name_help": "Lettres minuscules, chiffres, _ ou - · max 64",
    "indexer": "Indexer",
    "provider": "Provider",
    "model": "Modèle",
    "api_key_ref": "Référence clé d'API (Vault)",
    "api_key_ref_help_present": "Clé présente dans Harpocrate",
    "api_key_ref_help_missing": "Clé absente du vault",
    "base_url": "Base URL",
    "base_url_optional": "(optionnel — Ollama uniquement)"
  },
  "actions": {
    "rotate_apikey": "Régénérer l'api_key",
    "reindex": "Lancer une réindexation",
    "delete": "Supprimer"
  },
  "delete_dialog": {
    "title": "Supprimer {{name}} ?",
    "irreversible": "Cette action est irréversible. Conséquences :",
    "consequences": {
      "db": "La base pgvector rag_{{name}} sera droppée.",
      "docs": "Les {{count}} documents indexés seront perdus.",
      "apikey": "L'api_key du workspace sera révoquée immédiatement.",
      "agents": "Les agents utilisant cette api_key recevront 401."
    },
    "confirm_button": "Supprimer définitivement"
  },
  "toasts": {
    "created": "Workspace {{name}} créé.",
    "deleted": "Workspace {{name}} supprimé.",
    "apikey_rotated": "Nouvelle api_key pour {{name}}. À copier maintenant, elle ne s'affichera plus.",
    "reindex_started": "Réindexation de {{name}} démarrée."
  }
}
```

- [ ] **Step 3 : Créer les 4 fichiers en/ (miroirs anglais)**

`frontend/src/i18n/en/common.json` :
```json
{
  "buttons": {
    "cancel": "Cancel",
    "save": "Save",
    "create": "Create",
    "delete": "Delete",
    "confirm": "Confirm"
  },
  "loading": "Loading…",
  "errors": {
    "generic": "An error occurred, please retry.",
    "network": "Connection problem",
    "forbidden": "Insufficient permissions — contact an admin."
  }
}
```

`frontend/src/i18n/en/auth.json` :
```json
{
  "logout": "Sign out",
  "session_expired": "Session expired — please sign in again.",
  "not_configured": "OIDC is not configured. Admin must POST /admin/oidc."
}
```

`frontend/src/i18n/en/nav.json` :
```json
{
  "sections": {
    "administration": "Administration",
    "usage": "Usage"
  },
  "items": {
    "workspaces": "Workspaces",
    "sources": "Sources",
    "jobs": "Jobs",
    "models": "Models",
    "push": "Push activity",
    "mcp": "MCP search"
  }
}
```

`frontend/src/i18n/en/workspaces.json` :
```json
{
  "title": "Workspaces",
  "create": "Create workspace",
  "empty": {
    "title": "No workspace yet",
    "description": "Create your first workspace to start indexing content via git or synchronous push."
  },
  "table": {
    "name": "Name",
    "indexer": "Indexer",
    "sources": "Sources",
    "documents": "Documents",
    "last_indexed": "Last indexed",
    "actions": "Actions",
    "never": "Never"
  },
  "form": {
    "name": "Name",
    "name_help": "Lowercase letters, digits, _ or - · max 64",
    "indexer": "Indexer",
    "provider": "Provider",
    "model": "Model",
    "api_key_ref": "API key reference (Vault)",
    "api_key_ref_help_present": "Key present in Harpocrate",
    "api_key_ref_help_missing": "Key missing from vault",
    "base_url": "Base URL",
    "base_url_optional": "(optional — Ollama only)"
  },
  "actions": {
    "rotate_apikey": "Rotate api_key",
    "reindex": "Trigger reindex",
    "delete": "Delete"
  },
  "delete_dialog": {
    "title": "Delete {{name}}?",
    "irreversible": "This action is irreversible. Consequences:",
    "consequences": {
      "db": "The pgvector database rag_{{name}} will be dropped.",
      "docs": "The {{count}} indexed documents will be lost.",
      "apikey": "The workspace api_key will be revoked immediately.",
      "agents": "Agents using this api_key will receive 401."
    },
    "confirm_button": "Delete permanently"
  },
  "toasts": {
    "created": "Workspace {{name}} created.",
    "deleted": "Workspace {{name}} deleted.",
    "apikey_rotated": "New api_key for {{name}}. Copy it now, it won't be shown again.",
    "reindex_started": "Reindexing {{name}} started."
  }
}
```

- [ ] **Step 4 : Commit**

```powershell
git add frontend/src/lib/i18n.ts frontend/src/i18n/
git commit -m "feat(M5b): i18next config + namespaces fr/en (common, auth, nav, workspaces)"
```

---

## Task 6 : `lib/api.ts` (fetch wrapper) + tests

**Files:**
- Create: `frontend/src/lib/api.ts`
- Create: `frontend/tests/lib/api.test.ts`

- [ ] **Step 1 : Écrire les tests**

```ts
// frontend/tests/lib/api.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { api, ApiError, isUnauthorized } from "@/lib/api";

describe("api", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  describe("api.get", () => {
    it("returns parsed JSON on 200", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 200,
        json: async () => ({ name: "ws_a" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      const result = await api.get<{ name: string }>("/api/admin/workspaces/ws_a");
      expect(result).toEqual({ name: "ws_a" });
      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces/ws_a",
        expect.objectContaining({ credentials: "include" }),
      );
    });

    it("throws ApiError on 401", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        ok: false,
        status: 401,
        json: async () => ({ error: "oidc_session_missing" }),
      }));

      await expect(api.get("/me")).rejects.toMatchObject({
        name: "ApiError",
        status: 401,
      });
    });

    it("throws ApiError on 404 with body parsed", async () => {
      vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
        ok: false,
        status: 404,
        json: async () => ({ error: "workspace_not_found", name: "ghost" }),
      }));

      try {
        await api.get("/api/admin/workspaces/ghost");
        throw new Error("should have thrown");
      } catch (e) {
        expect(e).toBeInstanceOf(ApiError);
        expect((e as ApiError).status).toBe(404);
        expect((e as ApiError).body).toEqual({ error: "workspace_not_found", name: "ghost" });
      }
    });
  });

  describe("api.post", () => {
    it("sends body as JSON with credentials", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 201,
        json: async () => ({ name: "ws_a" }),
      });
      vi.stubGlobal("fetch", fetchMock);

      await api.post("/api/admin/workspaces", { name: "ws_a" });

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces",
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: "ws_a" }),
        }),
      );
    });
  });

  describe("api.delete", () => {
    it("sends DELETE with no body", async () => {
      const fetchMock = vi.fn().mockResolvedValue({
        ok: true,
        status: 204,
        json: async () => ({}),
      });
      vi.stubGlobal("fetch", fetchMock);

      await api.delete("/api/admin/workspaces/ws_a");

      expect(fetchMock).toHaveBeenCalledWith(
        "/api/admin/workspaces/ws_a",
        expect.objectContaining({ method: "DELETE", credentials: "include" }),
      );
    });
  });

  describe("isUnauthorized", () => {
    it("returns true for ApiError with status 401", () => {
      const err = new ApiError(401, { error: "x" });
      expect(isUnauthorized(err)).toBe(true);
    });

    it("returns false for non-401 ApiError", () => {
      const err = new ApiError(403, { error: "x" });
      expect(isUnauthorized(err)).toBe(false);
    });

    it("returns false for non-ApiError", () => {
      expect(isUnauthorized(new Error("oops"))).toBe(false);
    });
  });
});
```

- [ ] **Step 2 : Run tests to verify they fail**

```powershell
cd frontend
npm run test:run -- tests/lib/api.test.ts
```

Expected : `Cannot find module '@/lib/api'`.

- [ ] **Step 3 : Implémenter `src/lib/api.ts`**

```ts
// frontend/src/lib/api.ts
export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    super(`HTTP ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

export function isUnauthorized(err: unknown): boolean {
  return err instanceof ApiError && err.status === 401;
}

async function request<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    credentials: "include",  // envoyer cookies session OIDC
  });

  let body: unknown = null;
  try {
    body = await resp.json();
  } catch {
    // 204 No Content ou réponse non-JSON
  }

  if (!resp.ok) {
    throw new ApiError(resp.status, body);
  }

  return body as T;
}

export const api = {
  get: <T>(url: string): Promise<T> =>
    request<T>(url, { method: "GET" }),

  post: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  patch: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),

  delete: <T>(url: string): Promise<T> =>
    request<T>(url, { method: "DELETE" }),
};
```

- [ ] **Step 4 : Run tests to verify they pass**

```powershell
npm run test:run -- tests/lib/api.test.ts
```

Expected : `8 passed`.

- [ ] **Step 5 : Commit**

```powershell
git add frontend/src/lib/api.ts frontend/tests/lib/api.test.ts
git commit -m "feat(M5b): lib/api fetch wrapper avec ApiError + isUnauthorized + tests"
```

---

## Task 7 : `lib/validators.ts` (Zod) + tests

**Files:**
- Create: `frontend/src/lib/validators.ts`
- Create: `frontend/tests/lib/validators.test.ts`

- [ ] **Step 1 : Écrire les tests**

```ts
// frontend/tests/lib/validators.test.ts
import { describe, it, expect } from "vitest";
import { workspaceCreateSchema } from "@/lib/validators";

describe("workspaceCreateSchema", () => {
  it("accepts valid openai workspace", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "harpocrate",
      indexer: {
        provider: "openai",
        model: "text-embedding-3-small",
        api_key_ref: "openai_key",
      },
    });
    expect(result.success).toBe(true);
  });

  it("accepts valid ollama workspace without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws_ollama",
      indexer: {
        provider: "ollama",
        model: "nomic-embed-text",
        base_url: "http://192.168.10.80:11434",
      },
    });
    expect(result.success).toBe(true);
  });

  it("rejects empty name", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects uppercase name", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "BadName",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects name longer than 64 chars", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "a".repeat(65),
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects unknown provider", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      indexer: { provider: "nope", model: "x", api_key_ref: "k" },
    });
    expect(result.success).toBe(false);
  });

  it("rejects openai without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      indexer: { provider: "openai", model: "x" },
    });
    expect(result.success).toBe(false);
    if (!result.success) {
      expect(JSON.stringify(result.error.issues)).toContain("api_key_ref");
    }
  });

  it("accepts ollama without api_key_ref", () => {
    const result = workspaceCreateSchema.safeParse({
      name: "ws",
      indexer: { provider: "ollama", model: "x" },
    });
    expect(result.success).toBe(true);
  });
});
```

- [ ] **Step 2 : Run tests to verify they fail**

```powershell
npm run test:run -- tests/lib/validators.test.ts
```

Expected : `Cannot find module '@/lib/validators'`.

- [ ] **Step 3 : Implémenter `src/lib/validators.ts`**

```ts
// frontend/src/lib/validators.ts
import { z } from "zod";

export const workspaceCreateSchema = z
  .object({
    name: z
      .string()
      .min(1, "name_required")
      .max(64, "name_too_long")
      .regex(/^[a-z][a-z0-9_-]{0,62}$/, "name_invalid_format"),
    indexer: z.object({
      provider: z.enum(["openai", "voyage", "ollama"]),
      model: z.string().min(1, "model_required"),
      api_key_ref: z.string().min(1).optional(),
      base_url: z.string().url().optional(),
    }),
  })
  .refine(
    (data) => data.indexer.provider === "ollama" || !!data.indexer.api_key_ref,
    {
      message: "api_key_ref_required",
      path: ["indexer", "api_key_ref"],
    },
  );

export type WorkspaceCreate = z.infer<typeof workspaceCreateSchema>;

export interface Workspace {
  id: string;
  name: string;
  indexer: {
    provider: string;
    model: string;
    api_key_ref?: string;
    base_url?: string;
  };
  sources_count: number;
  documents_count: number;
  last_indexed_at: string | null;
  created_at: string;
}

export interface WorkspaceCreateResponse {
  name: string;
  api_key: string;  // affiché une seule fois côté UI
}

export interface ApiKeyRotateResponse {
  api_key: string;
}

export interface MeResponse {
  sub: string;
  email: string | null;
  name: string | null;
  roles: string[];
}
```

- [ ] **Step 4 : Run tests to verify they pass**

```powershell
npm run test:run -- tests/lib/validators.test.ts
```

Expected : `8 passed`.

- [ ] **Step 5 : Commit**

```powershell
git add frontend/src/lib/validators.ts frontend/tests/lib/validators.test.ts
git commit -m "feat(M5b): Zod validators + TypeScript types API + tests"
```

---

## Task 8 : `hooks/useMe.ts` + tests

**Files:**
- Create: `frontend/src/hooks/useMe.ts`
- Create: `frontend/tests/hooks/useMe.test.tsx`

- [ ] **Step 1 : Écrire les tests**

```tsx
// frontend/tests/hooks/useMe.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as apiModule from "@/lib/api";
import { useMe } from "@/hooks/useMe";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

describe("useMe", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("returns user data on success", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue({
      sub: "user-uuid",
      email: "test@example.com",
      name: "Test User",
      roles: ["rag-admin"],
    });

    const { result } = renderHook(() => useMe(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.email).toBe("test@example.com");
  });

  it("returns error on 401", async () => {
    vi.spyOn(apiModule.api, "get").mockRejectedValue(
      new apiModule.ApiError(401, { error: "oidc_session_missing" }),
    );

    const { result } = renderHook(() => useMe(), { wrapper: makeWrapper() });
    await waitFor(() => expect(result.current.isError).toBe(true));
    expect(apiModule.isUnauthorized(result.current.error)).toBe(true);
  });
});
```

- [ ] **Step 2 : Run tests to verify they fail**

```powershell
npm run test:run -- tests/hooks/useMe.test.tsx
```

Expected : `Cannot find module '@/hooks/useMe'`.

- [ ] **Step 3 : Implémenter `src/hooks/useMe.ts`**

```ts
// frontend/src/hooks/useMe.ts
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { MeResponse } from "@/lib/validators";

export function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: () => api.get<MeResponse>("/me"),
    retry: false,            // ne pas retry sur 401
    staleTime: 5 * 60 * 1000, // 5 min
  });
}
```

- [ ] **Step 4 : Run tests to verify they pass**

```powershell
npm run test:run -- tests/hooks/useMe.test.tsx
```

Expected : `2 passed`.

- [ ] **Step 5 : Commit**

```powershell
git add frontend/src/hooks/useMe.ts frontend/tests/hooks/useMe.test.tsx
git commit -m "feat(M5b): useMe hook (GET /me) + tests"
```

---

## Task 9 : shadcn/ui composants — Button, Input, Label, Select, Card, Badge

**Files:**
- Create: `frontend/src/components/ui/button.tsx`
- Create: `frontend/src/components/ui/input.tsx`
- Create: `frontend/src/components/ui/label.tsx`
- Create: `frontend/src/components/ui/select.tsx`
- Create: `frontend/src/components/ui/card.tsx`
- Create: `frontend/src/components/ui/badge.tsx`

Note : ces fichiers sont des copies des composants shadcn officiels. Pas de tests dédiés (réputés par la communauté shadcn). Copiez-collez les versions actuelles depuis [ui.shadcn.com](https://ui.shadcn.com).

- [ ] **Step 1 : Créer `button.tsx`**

```tsx
// frontend/src/components/ui/button.tsx
import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-primary text-primary-foreground shadow hover:bg-primary/90",
        destructive: "bg-destructive text-destructive-foreground shadow-sm hover:bg-destructive/90",
        outline: "border border-input bg-background shadow-sm hover:bg-accent hover:text-accent-foreground",
        secondary: "bg-secondary text-secondary-foreground shadow-sm hover:bg-secondary/80",
        ghost: "hover:bg-accent hover:text-accent-foreground",
        link: "text-primary underline-offset-4 hover:underline",
      },
      size: {
        default: "h-9 px-4 py-2",
        sm: "h-8 rounded-md px-3 text-xs",
        lg: "h-10 rounded-md px-8",
        icon: "h-9 w-9",
      },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp className={cn(buttonVariants({ variant, size, className }))} ref={ref} {...props} />
    );
  },
);
Button.displayName = "Button";

export { Button, buttonVariants };
```

- [ ] **Step 2 : Créer `input.tsx`**

```tsx
// frontend/src/components/ui/input.tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => {
    return (
      <input
        type={type}
        className={cn(
          "flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        ref={ref}
        {...props}
      />
    );
  },
);
Input.displayName = "Input";

export { Input };
```

- [ ] **Step 3 : Créer `label.tsx`**

```tsx
// frontend/src/components/ui/label.tsx
import * as React from "react";
import * as LabelPrimitive from "@radix-ui/react-label";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const labelVariants = cva(
  "text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70",
);

const Label = React.forwardRef<
  React.ElementRef<typeof LabelPrimitive.Root>,
  React.ComponentPropsWithoutRef<typeof LabelPrimitive.Root> & VariantProps<typeof labelVariants>
>(({ className, ...props }, ref) => (
  <LabelPrimitive.Root ref={ref} className={cn(labelVariants(), className)} {...props} />
));
Label.displayName = LabelPrimitive.Root.displayName;

export { Label };
```

- [ ] **Step 4 : Créer `select.tsx`**

Note : composant shadcn/ui select complet — récupère le contenu depuis [ui.shadcn.com/docs/components/select](https://ui.shadcn.com/docs/components/select) tel quel (l'API est stable). Si tu n'as pas accès web, le pattern : `Select`, `SelectGroup`, `SelectValue`, `SelectTrigger`, `SelectContent`, `SelectLabel`, `SelectItem`, `SelectSeparator`, `SelectScrollUpButton`, `SelectScrollDownButton`. Tous wrapping `@radix-ui/react-select`. ~140 lignes.

Copie-colle le fichier source officiel (vérifié stable au moment du plan).

- [ ] **Step 5 : Créer `card.tsx`**

```tsx
// frontend/src/components/ui/card.tsx
import * as React from "react";
import { cn } from "@/lib/utils";

const Card = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div
      ref={ref}
      className={cn("rounded-xl border bg-card text-card-foreground shadow", className)}
      {...props}
    />
  ),
);
Card.displayName = "Card";

const CardHeader = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("flex flex-col space-y-1.5 p-6", className)} {...props} />
  ),
);
CardHeader.displayName = "CardHeader";

const CardTitle = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("font-semibold leading-none tracking-tight", className)} {...props} />
  ),
);
CardTitle.displayName = "CardTitle";

const CardContent = React.forwardRef<HTMLDivElement, React.HTMLAttributes<HTMLDivElement>>(
  ({ className, ...props }, ref) => (
    <div ref={ref} className={cn("p-6 pt-0", className)} {...props} />
  ),
);
CardContent.displayName = "CardContent";

export { Card, CardHeader, CardTitle, CardContent };
```

- [ ] **Step 6 : Créer `badge.tsx`**

```tsx
// frontend/src/components/ui/badge.tsx
import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "@/lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-md border px-2.5 py-0.5 text-xs font-semibold transition-colors focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        secondary: "border-transparent bg-secondary text-secondary-foreground",
        destructive: "border-transparent bg-destructive text-destructive-foreground",
        outline: "text-foreground",
      },
    },
    defaultVariants: { variant: "default" },
  },
);

export interface BadgeProps
  extends React.HTMLAttributes<HTMLDivElement>,
    VariantProps<typeof badgeVariants> {}

function Badge({ className, variant, ...props }: BadgeProps) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}

export { Badge, badgeVariants };
```

- [ ] **Step 7 : Commit**

```powershell
git add frontend/src/components/ui/
git commit -m "feat(M5b): shadcn/ui composants base (button, input, label, select, card, badge)"
```

---

## Task 10 : shadcn/ui composants — Table, Dialog, AlertDialog, DropdownMenu, Form, Toast

**Files:**
- Create: `frontend/src/components/ui/table.tsx`
- Create: `frontend/src/components/ui/dialog.tsx`
- Create: `frontend/src/components/ui/alert-dialog.tsx`
- Create: `frontend/src/components/ui/dropdown-menu.tsx`
- Create: `frontend/src/components/ui/form.tsx`
- Create: `frontend/src/components/ui/toast.tsx`
- Create: `frontend/src/components/ui/toaster.tsx`

- [ ] **Step 1 : Copier les composants depuis shadcn**

Pour chaque fichier, copier le code source officiel depuis [ui.shadcn.com](https://ui.shadcn.com). Ces composants sont copy-paste par convention :

- `table.tsx` : ~80 lignes, wrappers HTML purs (Table/TableHeader/TableBody/TableRow/TableHead/TableCell)
- `dialog.tsx` : ~120 lignes, wrappers `@radix-ui/react-dialog`
- `alert-dialog.tsx` : ~140 lignes, wrappers `@radix-ui/react-alert-dialog`
- `dropdown-menu.tsx` : ~200 lignes, wrappers `@radix-ui/react-dropdown-menu`
- `form.tsx` : ~170 lignes, intégration `react-hook-form` (FormProvider, FormField, FormItem, FormLabel, FormControl, FormDescription, FormMessage)
- `toast.tsx` + `toaster.tsx` : ~140 + ~40 lignes, wrappers `@radix-ui/react-toast` + provider

Le fichier `toaster.tsx` doit être monté à la racine de l'app (cf. Task 16 : ajout dans `App.tsx`).

- [ ] **Step 2 : Vérifier typecheck**

```powershell
npm run typecheck
```

Expected : 0 erreurs. Si erreurs sur les composants shadcn (versions Radix incompatibles), ajuster les peer dependencies.

- [ ] **Step 3 : Commit**

```powershell
git add frontend/src/components/ui/
git commit -m "feat(M5b): shadcn/ui composants avancés (table, dialog, alert-dialog, dropdown-menu, form, toast)"
```

---

## Task 11 : `components/AuthGuard.tsx` + `LoadingSpinner.tsx` + tests

**Files:**
- Create: `frontend/src/components/AuthGuard.tsx`
- Create: `frontend/src/components/LoadingSpinner.tsx`
- Create: `frontend/tests/components/AuthGuard.test.tsx`

- [ ] **Step 1 : Écrire les tests**

```tsx
// frontend/tests/components/AuthGuard.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { AuthGuard } from "@/components/AuthGuard";
import * as apiModule from "@/lib/api";

const _origLocation = window.location;

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("AuthGuard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    // Mock window.location pour vérifier le redirect
    delete (window as { location?: Location }).location;
    window.location = { ...(_origLocation), href: "/ui/workspaces", pathname: "/ui/workspaces", search: "" } as Location;
  });

  it("shows loading spinner while fetching /me", () => {
    vi.spyOn(apiModule.api, "get").mockImplementation(() => new Promise(() => {}));

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    expect(screen.queryByText("child")).not.toBeInTheDocument();
    expect(screen.getByRole("status")).toBeInTheDocument();
  });

  it("renders children when /me succeeds", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue({
      sub: "u", email: "e@x.com", name: "X", roles: ["rag-admin"],
    });

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    await waitFor(() => expect(screen.getByText("child")).toBeInTheDocument());
  });

  it("redirects to /auth/login on 401", async () => {
    vi.spyOn(apiModule.api, "get").mockRejectedValue(
      new apiModule.ApiError(401, { error: "oidc_session_missing" }),
    );

    render(
      <Wrapper>
        <AuthGuard>
          <div>child</div>
        </AuthGuard>
      </Wrapper>,
    );

    await waitFor(() => {
      expect(window.location.href).toBe(
        "/auth/login?next=" + encodeURIComponent("/ui/workspaces"),
      );
    });
  });
});
```

- [ ] **Step 2 : Run tests to verify they fail**

```powershell
npm run test:run -- tests/components/AuthGuard.test.tsx
```

Expected : `Cannot find module '@/components/AuthGuard'`.

- [ ] **Step 3 : Implémenter `LoadingSpinner.tsx`**

```tsx
// frontend/src/components/LoadingSpinner.tsx
import { Loader2 } from "lucide-react";

export function LoadingSpinner() {
  return (
    <div role="status" className="flex items-center justify-center min-h-[40vh]">
      <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      <span className="sr-only">Loading</span>
    </div>
  );
}
```

- [ ] **Step 4 : Implémenter `AuthGuard.tsx` + `UserContext`**

```tsx
// frontend/src/components/AuthGuard.tsx
import { createContext, useContext, type ReactNode } from "react";
import { useMe } from "@/hooks/useMe";
import { isUnauthorized } from "@/lib/api";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { MeResponse } from "@/lib/validators";

const UserContext = createContext<MeResponse | null>(null);

export function useUser(): MeResponse {
  const ctx = useContext(UserContext);
  if (!ctx) throw new Error("useUser must be inside AuthGuard");
  return ctx;
}

export function AuthGuard({ children }: { children: ReactNode }) {
  const { data, error, isLoading } = useMe();

  if (isLoading) return <LoadingSpinner />;

  if (error && isUnauthorized(error)) {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/auth/login?next=${encodeURIComponent(next)}`;
    return null;
  }

  if (!data) {
    return (
      <div className="p-6 text-center text-destructive">
        Authentication failed. Please refresh.
      </div>
    );
  }

  return <UserContext.Provider value={data}>{children}</UserContext.Provider>;
}
```

- [ ] **Step 5 : Run tests to verify they pass**

```powershell
npm run test:run -- tests/components/AuthGuard.test.tsx
```

Expected : `3 passed`.

- [ ] **Step 6 : Commit**

```powershell
git add frontend/src/components/AuthGuard.tsx frontend/src/components/LoadingSpinner.tsx frontend/tests/components/AuthGuard.test.tsx
git commit -m "feat(M5b): AuthGuard + UserContext + LoadingSpinner + tests"
```

---

## Task 12 : `Sidebar.tsx` + `Header.tsx` (layout shell D1 v2)

**Files:**
- Create: `frontend/src/components/Sidebar.tsx`
- Create: `frontend/src/components/Header.tsx`

Note : pas de tests dédiés (composants visuels purs sans logique métier). Couvert par les tests de WorkspacesPage qui les rendent indirectement.

- [ ] **Step 1 : Créer `Sidebar.tsx` (style D1 v2)**

```tsx
// frontend/src/components/Sidebar.tsx
import { NavLink } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  LayoutGrid, GitBranch, Clock, Database, Send, Search,
} from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItemProps {
  to: string;
  icon: React.ReactNode;
  label: string;
  disabled?: boolean;
}

function NavItem({ to, icon, label, disabled = false }: NavItemProps) {
  if (disabled) {
    return (
      <div
        className="mx-2 my-0.5 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm font-medium text-slate-500 cursor-not-allowed select-none"
        aria-disabled="true"
      >
        <span className="text-slate-400 [&>svg]:h-4 [&>svg]:w-4">{icon}</span>
        <span>{label}</span>
      </div>
    );
  }

  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "mx-2 my-0.5 flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
          isActive
            ? "bg-primary text-primary-foreground font-bold"
            : "text-slate-900 font-semibold hover:bg-slate-100",
        )
      }
    >
      {({ isActive }) => (
        <>
          <span
            className={cn(
              "[&>svg]:h-4 [&>svg]:w-4",
              isActive ? "text-primary-foreground" : "text-slate-700",
            )}
          >
            {icon}
          </span>
          <span>{label}</span>
        </>
      )}
    </NavLink>
  );
}

export function Sidebar() {
  const { t } = useTranslation("nav");

  return (
    <aside className="w-[220px] flex-shrink-0 border-r border-slate-200 bg-zinc-50 flex flex-col">
      <div className="px-5 py-4 border-b border-slate-100 flex items-center gap-2">
        <div className="h-6 w-6 rounded-md bg-gradient-to-br from-sky-600 to-sky-500" />
        <span className="font-semibold text-slate-900">ag-flow.rag</span>
      </div>

      <nav className="flex-1 py-3">
        <div className="px-5 pt-3 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.administration")}
        </div>
        <NavItem to="/workspaces" icon={<LayoutGrid />} label={t("items.workspaces")} />
        <NavItem to="/sources" icon={<GitBranch />} label={t("items.sources")} disabled />
        <NavItem to="/jobs" icon={<Clock />} label={t("items.jobs")} disabled />
        <NavItem to="/models" icon={<Database />} label={t("items.models")} disabled />

        <div className="px-5 pt-4 pb-1 text-xs font-bold uppercase tracking-wider text-slate-600">
          {t("sections.usage")}
        </div>
        <NavItem to="/push" icon={<Send />} label={t("items.push")} disabled />
        <NavItem to="/mcp" icon={<Search />} label={t("items.mcp")} disabled />
      </nav>
    </aside>
  );
}
```

- [ ] **Step 2 : Créer `Header.tsx`**

```tsx
// frontend/src/components/Header.tsx
import { useUser } from "@/components/AuthGuard";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { LogOut, ChevronDown } from "lucide-react";

export function Header() {
  const { t } = useTranslation("auth");
  const user = useUser();

  const initials = (user.name ?? user.email ?? "?")
    .split(/\s+/)
    .map((s) => s[0])
    .slice(0, 2)
    .join("")
    .toUpperCase();

  function handleLogout() {
    // POST /auth/logout (cookie envoyé), backend redirige vers Keycloak logout.
    // On utilise un form submit pour préserver les redirects 302.
    const form = document.createElement("form");
    form.method = "POST";
    form.action = "/auth/logout";
    document.body.appendChild(form);
    form.submit();
  }

  return (
    <header className="bg-white border-b border-slate-200 px-6 py-3 flex items-center justify-between">
      <div /> {/* page title can be added via portal later */}

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="sm" className="gap-2">
            <span className="h-7 w-7 rounded-full bg-primary text-primary-foreground flex items-center justify-center text-xs font-semibold">
              {initials}
            </span>
            <span className="text-sm text-slate-700">{user.email ?? user.sub}</span>
            <ChevronDown className="h-4 w-4 text-slate-400" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" />
            {t("logout")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );
}
```

- [ ] **Step 3 : Commit**

```powershell
git add frontend/src/components/Sidebar.tsx frontend/src/components/Header.tsx
git commit -m "feat(M5b): layout shell Sidebar (D1 v2) + Header user dropdown"
```

---

## Task 13 : `hooks/useWorkspaces.ts` (5 hooks CRUD) + tests

**Files:**
- Create: `frontend/src/hooks/useWorkspaces.ts`
- Create: `frontend/src/hooks/useToast.ts`
- Create: `frontend/tests/hooks/useWorkspaces.test.tsx`

- [ ] **Step 1 : Créer `useToast.ts` (re-export shadcn)**

```ts
// frontend/src/hooks/useToast.ts
// Re-export shadcn useToast for unified import path.
export { useToast, toast } from "@/components/ui/use-toast";
```

Note : si le composant `toast.tsx` shadcn ne fournit pas `useToast` hook, créer `frontend/src/components/ui/use-toast.ts` selon le pattern shadcn (~150 lignes — reducer + state machine pour les toasts). À copier depuis [ui.shadcn.com](https://ui.shadcn.com) tel quel.

- [ ] **Step 2 : Écrire les tests**

```tsx
// frontend/tests/hooks/useWorkspaces.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import * as apiModule from "@/lib/api";
import {
  useWorkspaces,
  useCreateWorkspace,
  useDeleteWorkspace,
  useRotateApiKey,
  useReindex,
} from "@/hooks/useWorkspaces";

function makeWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  return { qc, wrapper: ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  )};
}

describe("useWorkspaces hooks", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("useWorkspaces fetches the list", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      { id: "1", name: "ws_a", indexer: { provider: "openai", model: "x" }, sources_count: 0, documents_count: 0, last_indexed_at: null, created_at: "" },
    ]);

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useWorkspaces(), { wrapper });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.[0]?.name).toBe("ws_a");
  });

  it("useCreateWorkspace POSTs and invalidates", async () => {
    vi.spyOn(apiModule.api, "post").mockResolvedValue({ name: "ws_a", api_key: "key-xyz" });

    const { qc, wrapper } = makeWrapper();
    const invalidateSpy = vi.spyOn(qc, "invalidateQueries");

    const { result } = renderHook(() => useCreateWorkspace(), { wrapper });
    result.current.mutate({
      name: "ws_a",
      indexer: { provider: "openai", model: "x", api_key_ref: "k" },
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ["workspaces"] });
  });

  it("useDeleteWorkspace DELETEs by name", async () => {
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockResolvedValue({});

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useDeleteWorkspace(), { wrapper });

    result.current.mutate("ws_a");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(deleteSpy).toHaveBeenCalledWith("/api/admin/workspaces/ws_a");
  });

  it("useRotateApiKey POSTs and returns new key", async () => {
    vi.spyOn(apiModule.api, "post").mockResolvedValue({ api_key: "new-key" });

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useRotateApiKey(), { wrapper });

    result.current.mutate("ws_a");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data?.api_key).toBe("new-key");
  });

  it("useReindex POSTs with ?confirm=true", async () => {
    const postSpy = vi.spyOn(apiModule.api, "post").mockResolvedValue({});

    const { wrapper } = makeWrapper();
    const { result } = renderHook(() => useReindex(), { wrapper });

    result.current.mutate("ws_a");
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(postSpy).toHaveBeenCalledWith(
      "/api/admin/workspaces/ws_a/reindex?confirm=true",
      {},
    );
  });
});
```

- [ ] **Step 3 : Run tests to verify they fail**

```powershell
npm run test:run -- tests/hooks/useWorkspaces.test.tsx
```

Expected : `Cannot find module '@/hooks/useWorkspaces'`.

- [ ] **Step 4 : Implémenter `useWorkspaces.ts`**

```ts
// frontend/src/hooks/useWorkspaces.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type {
  ApiKeyRotateResponse,
  Workspace,
  WorkspaceCreate,
  WorkspaceCreateResponse,
} from "@/lib/validators";

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.get<Workspace[]>("/api/admin/workspaces"),
  });
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: WorkspaceCreate) =>
      api.post<WorkspaceCreateResponse>("/api/admin/workspaces", payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api.delete<void>(`/api/admin/workspaces/${name}`),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useRotateApiKey() {
  return useMutation({
    mutationFn: (name: string) =>
      api.post<ApiKeyRotateResponse>(
        `/api/admin/workspaces/${name}/rotate-apikey`,
        {},
      ),
  });
}

export function useReindex() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) =>
      api.post<void>(
        `/api/admin/workspaces/${name}/reindex?confirm=true`,
        {},
      ),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}
```

- [ ] **Step 5 : Run tests to verify they pass**

```powershell
npm run test:run -- tests/hooks/useWorkspaces.test.tsx
```

Expected : `5 passed`.

- [ ] **Step 6 : Commit**

```powershell
git add frontend/src/hooks/useWorkspaces.ts frontend/src/hooks/useToast.ts frontend/tests/hooks/useWorkspaces.test.tsx
git commit -m "feat(M5b): hooks useWorkspaces (5 CRUD) + useToast + tests"
```

---

## Task 14 : `pages/WorkspacesPage.tsx` (liste + empty state) + tests

**Files:**
- Create: `frontend/src/components/StatusIndicator.tsx`
- Create: `frontend/src/pages/WorkspacesPage.tsx`
- Create: `frontend/tests/components/StatusIndicator.test.tsx`
- Create: `frontend/tests/pages/WorkspacesPage.test.tsx`

- [ ] **Step 1 : Créer `StatusIndicator.tsx`**

```tsx
// frontend/src/components/StatusIndicator.tsx
import { cn } from "@/lib/utils";

export type SecretStatus = "present" | "empty" | "missing";

interface Props {
  status: SecretStatus;
  className?: string;
}

const dotClass: Record<SecretStatus, string> = {
  present: "bg-emerald-500",
  empty: "bg-amber-500",
  missing: "bg-red-500",
};

export function StatusIndicator({ status, className }: Props) {
  return (
    <span
      role="status"
      aria-label={`secret-${status}`}
      className={cn("inline-block h-2.5 w-2.5 rounded-full", dotClass[status], className)}
    />
  );
}
```

- [ ] **Step 2 : Écrire les tests de StatusIndicator**

```tsx
// frontend/tests/components/StatusIndicator.test.tsx
import { describe, it, expect } from "vitest";
import { render, screen } from "@testing-library/react";
import { StatusIndicator } from "@/components/StatusIndicator";

describe("StatusIndicator", () => {
  it("renders green dot for present", () => {
    render(<StatusIndicator status="present" />);
    const el = screen.getByRole("status");
    expect(el).toHaveAttribute("aria-label", "secret-present");
    expect(el.className).toContain("bg-emerald-500");
  });

  it("renders orange dot for empty", () => {
    render(<StatusIndicator status="empty" />);
    expect(screen.getByRole("status").className).toContain("bg-amber-500");
  });

  it("renders red dot for missing", () => {
    render(<StatusIndicator status="missing" />);
    expect(screen.getByRole("status").className).toContain("bg-red-500");
  });
});
```

- [ ] **Step 3 : Run tests**

```powershell
npm run test:run -- tests/components/StatusIndicator.test.tsx
```

Expected : `3 passed`.

- [ ] **Step 4 : Écrire le test de WorkspacesPage**

```tsx
// frontend/tests/pages/WorkspacesPage.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import "@/lib/i18n";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import * as apiModule from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <MemoryRouter>{children}</MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkspacesPage", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("shows empty state when workspaces list is empty", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText(/aucun workspace/i)).toBeInTheDocument();
    });
  });

  it("renders the table with workspaces data", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([
      {
        id: "1", name: "harpocrate",
        indexer: { provider: "openai", model: "text-embedding-3-small" },
        sources_count: 3, documents_count: 412,
        last_indexed_at: "2026-05-16T10:00:00Z", created_at: "2026-01-01T00:00:00Z",
      },
    ]);

    render(<WorkspacesPage />, { wrapper: Wrapper });

    await waitFor(() => {
      expect(screen.getByText("harpocrate")).toBeInTheDocument();
      expect(screen.getByText("412")).toBeInTheDocument();
      expect(screen.getByText(/openai\/text-embedding-3-small/)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 5 : Implémenter `WorkspacesPage.tsx` (sans le dialog/actions encore)**

```tsx
// frontend/src/pages/WorkspacesPage.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { WorkspaceCreateDialog } from "@/pages/WorkspaceCreateDialog";
import { WorkspaceActions } from "@/pages/WorkspaceActions";

export function WorkspacesPage() {
  const { t } = useTranslation("workspaces");
  const { data, isLoading } = useWorkspaces();
  const [createOpen, setCreateOpen] = useState(false);

  if (isLoading) return <LoadingSpinner />;

  const workspaces = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">{t("title")}</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          {t("create")}
        </Button>
      </div>

      {workspaces.length === 0 ? (
        <EmptyState onCreate={() => setCreateOpen(true)} />
      ) : (
        <div className="rounded-md border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("table.name")}</TableHead>
                <TableHead>{t("table.indexer")}</TableHead>
                <TableHead>{t("table.sources")}</TableHead>
                <TableHead>{t("table.documents")}</TableHead>
                <TableHead>{t("table.last_indexed")}</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {workspaces.map((ws) => (
                <TableRow key={ws.id}>
                  <TableCell className="font-medium">{ws.name}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-mono text-xs">
                      {ws.indexer.provider}/{ws.indexer.model}
                    </Badge>
                  </TableCell>
                  <TableCell>{ws.sources_count}</TableCell>
                  <TableCell>{ws.documents_count}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {ws.last_indexed_at ? formatRelative(ws.last_indexed_at) : t("table.never")}
                  </TableCell>
                  <TableCell>
                    <WorkspaceActions workspace={ws} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <WorkspaceCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation("workspaces");
  return (
    <div className="mx-auto mt-16 max-w-md text-center rounded-lg border border-dashed border-slate-300 p-10">
      <FolderOpen className="mx-auto mb-3 h-10 w-10 text-slate-400" />
      <h3 className="text-base font-semibold text-slate-900 mb-1.5">
        {t("empty.title")}
      </h3>
      <p className="text-sm text-slate-500 mb-5">{t("empty.description")}</p>
      <Button onClick={onCreate}>
        <Plus className="h-4 w-4" />
        {t("create")}
      </Button>
    </div>
  );
}

function formatRelative(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days} j`;
}
```

Note : ce fichier référence `WorkspaceCreateDialog` et `WorkspaceActions` qui n'existent pas encore. On va les créer en T15.

- [ ] **Step 6 : Créer stubs temporaires pour `WorkspaceCreateDialog` et `WorkspaceActions`**

Avant que T15 ne crée les vrais, on a besoin de stubs pour que les tests passent.

`frontend/src/pages/WorkspaceCreateDialog.tsx` (stub) :
```tsx
interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceCreateDialog({ open: _open, onOpenChange: _onOpenChange }: Props) {
  return null;
}
```

`frontend/src/pages/WorkspaceActions.tsx` (stub) :
```tsx
import type { Workspace } from "@/lib/validators";

export function WorkspaceActions({ workspace: _workspace }: { workspace: Workspace }) {
  return null;
}
```

- [ ] **Step 7 : Run tests**

```powershell
npm run test:run -- tests/pages/WorkspacesPage.test.tsx
```

Expected : `2 passed`.

- [ ] **Step 8 : Commit**

```powershell
git add frontend/src/components/StatusIndicator.tsx frontend/src/pages/WorkspacesPage.tsx frontend/src/pages/WorkspaceCreateDialog.tsx frontend/src/pages/WorkspaceActions.tsx frontend/tests/components/StatusIndicator.test.tsx frontend/tests/pages/WorkspacesPage.test.tsx
git commit -m "feat(M5b): page WorkspacesPage (liste + empty state) + StatusIndicator + stubs"
```

---

## Task 15 : `WorkspaceCreateDialog.tsx` (form react-hook-form + Zod) + tests

**Files:**
- Modify: `frontend/src/pages/WorkspaceCreateDialog.tsx`
- Create: `frontend/tests/pages/WorkspaceCreateDialog.test.tsx`

- [ ] **Step 1 : Implémenter `WorkspaceCreateDialog.tsx`**

```tsx
// frontend/src/pages/WorkspaceCreateDialog.tsx
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useCreateWorkspace } from "@/hooks/useWorkspaces";
import { workspaceCreateSchema, type WorkspaceCreate } from "@/lib/validators";
import { useToast } from "@/hooks/useToast";

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["text-embedding-3-small", "text-embedding-3-large"],
  voyage: ["voyage-3", "voyage-3-lite"],
  ollama: ["nomic-embed-text", "mxbai-embed-large"],
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceCreateDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const createMutation = useCreateWorkspace();

  const form = useForm<WorkspaceCreate>({
    resolver: zodResolver(workspaceCreateSchema),
    defaultValues: {
      name: "",
      indexer: {
        provider: "openai",
        model: "text-embedding-3-small",
        api_key_ref: "",
      },
    },
  });

  const provider = form.watch("indexer.provider");
  const models = MODELS_BY_PROVIDER[provider] ?? [];

  async function onSubmit(values: WorkspaceCreate) {
    try {
      const resp = await createMutation.mutateAsync(values);
      toast({ title: t("toasts.created", { name: resp.name }) });
      onOpenChange(false);
      form.reset();
    } catch (err) {
      toast({
        title: t("common:errors.generic"),
        variant: "destructive",
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("create")}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("form.name")}</FormLabel>
                  <FormControl>
                    <Input placeholder="harpocrate" {...field} />
                  </FormControl>
                  <FormDescription>{t("form.name_help")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="border-t pt-4">
              <div className="text-xs font-bold uppercase tracking-wide text-slate-600 mb-3">
                {t("form.indexer")}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <FormField
                  control={form.control}
                  name="indexer.provider"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.provider")}</FormLabel>
                      <Select
                        onValueChange={(v) => {
                          field.onChange(v);
                          // Reset model when provider changes
                          form.setValue("indexer.model", MODELS_BY_PROVIDER[v]?.[0] ?? "");
                        }}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="openai">openai</SelectItem>
                          <SelectItem value="voyage">voyage</SelectItem>
                          <SelectItem value="ollama">ollama</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="indexer.model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.model")}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {models.map((m) => (
                            <SelectItem key={m} value={m}>{m}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
              </div>

              {provider !== "ollama" && (
                <FormField
                  control={form.control}
                  name="indexer.api_key_ref"
                  render={({ field }) => (
                    <FormItem className="mt-3">
                      <FormLabel>{t("form.api_key_ref")}</FormLabel>
                      <FormControl>
                        <Input placeholder="openai_embedding_key" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {provider === "ollama" && (
                <FormField
                  control={form.control}
                  name="indexer.base_url"
                  render={({ field }) => (
                    <FormItem className="mt-3">
                      <FormLabel>
                        {t("form.base_url")}{" "}
                        <span className="text-slate-400 font-normal">{t("form.base_url_optional")}</span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="http://192.168.10.80:11434" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("common:buttons.cancel")}
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {t("common:buttons.create")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2 : Écrire les tests**

```tsx
// frontend/tests/pages/WorkspaceCreateDialog.test.tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import "@/lib/i18n";
import { WorkspaceCreateDialog } from "@/pages/WorkspaceCreateDialog";
import * as apiModule from "@/lib/api";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { mutations: { retry: false } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("WorkspaceCreateDialog", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("renders form fields when open", () => {
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    expect(screen.getByLabelText(/^nom$/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/provider/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/modèle/i)).toBeInTheDocument();
  });

  it("shows base_url field only for ollama provider", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    // Initially openai → api_key_ref visible, base_url not
    expect(screen.getByLabelText(/référence clé d'api/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/base url/i)).not.toBeInTheDocument();

    // Switch to ollama
    await user.click(screen.getByLabelText(/provider/i));
    await user.click(screen.getByText("ollama"));

    await waitFor(() => {
      expect(screen.getByLabelText(/base url/i)).toBeInTheDocument();
    });
  });

  it("submits valid form and calls api.post", async () => {
    const postSpy = vi
      .spyOn(apiModule.api, "post")
      .mockResolvedValue({ name: "test_ws", api_key: "key" });
    const user = userEvent.setup();
    const onOpenChange = vi.fn();

    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={onOpenChange} />
      </Wrapper>,
    );

    await user.type(screen.getByLabelText(/^nom$/i), "test_ws");
    await user.type(screen.getByLabelText(/référence clé d'api/i), "openai_key");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      expect(postSpy).toHaveBeenCalledWith(
        "/api/admin/workspaces",
        expect.objectContaining({
          name: "test_ws",
          indexer: expect.objectContaining({
            provider: "openai",
            api_key_ref: "openai_key",
          }),
        }),
      );
    });
  });

  it("validates name format (lowercase only)", async () => {
    const user = userEvent.setup();
    render(
      <Wrapper>
        <WorkspaceCreateDialog open={true} onOpenChange={() => {}} />
      </Wrapper>,
    );

    await user.type(screen.getByLabelText(/^nom$/i), "BadName");
    await user.type(screen.getByLabelText(/référence clé d'api/i), "key");
    await user.click(screen.getByRole("button", { name: /créer/i }));

    await waitFor(() => {
      // Zod error message displayed
      expect(screen.getByText(/name_invalid_format/i)).toBeInTheDocument();
    });
  });
});
```

- [ ] **Step 3 : Run tests**

```powershell
npm run test:run -- tests/pages/WorkspaceCreateDialog.test.tsx
```

Expected : `4 passed`. Si la sélection du provider échoue (Radix UI portals), peut nécessiter un mock plus subtil — adapter le test pour utiliser `screen.getByRole("combobox")` ou `screen.findByText` au lieu de getByLabelText.

- [ ] **Step 4 : Commit**

```powershell
git add frontend/src/pages/WorkspaceCreateDialog.tsx frontend/tests/pages/WorkspaceCreateDialog.test.tsx
git commit -m "feat(M5b): WorkspaceCreateDialog (form react-hook-form + Zod + conditional Ollama)"
```

---

## Task 16 : `WorkspaceActions.tsx` (dropdown menu) + `WorkspaceDeleteAlert.tsx`

**Files:**
- Modify: `frontend/src/pages/WorkspaceActions.tsx`
- Create: `frontend/src/pages/WorkspaceDeleteAlert.tsx`

- [ ] **Step 1 : Implémenter `WorkspaceDeleteAlert.tsx`**

```tsx
// frontend/src/pages/WorkspaceDeleteAlert.tsx
import { useTranslation } from "react-i18next";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel,
  AlertDialogContent, AlertDialogDescription, AlertDialogFooter,
  AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteWorkspace } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";
import type { Workspace } from "@/lib/validators";

interface Props {
  workspace: Workspace;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceDeleteAlert({ workspace, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const deleteMutation = useDeleteWorkspace();

  async function handleDelete() {
    try {
      await deleteMutation.mutateAsync(workspace.name);
      toast({ title: t("toasts.deleted", { name: workspace.name }) });
      onOpenChange(false);
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            ⚠ {t("delete_dialog.title", { name: workspace.name })}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>
              <p className="mb-2">{t("delete_dialog.irreversible")}</p>
              <ul className="list-disc pl-5 text-sm space-y-1 text-slate-700">
                <li>{t("delete_dialog.consequences.db", { name: workspace.name })}</li>
                <li>{t("delete_dialog.consequences.docs", { count: workspace.documents_count })}</li>
                <li>{t("delete_dialog.consequences.apikey")}</li>
                <li>{t("delete_dialog.consequences.agents")}</li>
              </ul>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common:buttons.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {t("delete_dialog.confirm_button")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 2 : Implémenter `WorkspaceActions.tsx`**

```tsx
// frontend/src/pages/WorkspaceActions.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreVertical, KeyRound, RotateCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem,
  DropdownMenuSeparator, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { WorkspaceDeleteAlert } from "@/pages/WorkspaceDeleteAlert";
import { useRotateApiKey, useReindex } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";
import type { Workspace } from "@/lib/validators";

export function WorkspaceActions({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const rotateMutation = useRotateApiKey();
  const reindexMutation = useReindex();

  async function handleRotate() {
    try {
      const resp = await rotateMutation.mutateAsync(workspace.name);
      toast({
        title: t("toasts.apikey_rotated", { name: workspace.name }),
        description: resp.api_key,
        duration: 30_000,  // 30s pour le user puisse copier
      });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  async function handleReindex() {
    try {
      await reindexMutation.mutateAsync(workspace.name);
      toast({ title: t("toasts.reindex_started", { name: workspace.name }) });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem onClick={handleRotate}>
            <KeyRound className="h-4 w-4 mr-2" />
            {t("actions.rotate_apikey")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleReindex}>
            <RotateCw className="h-4 w-4 mr-2" />
            {t("actions.reindex")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setDeleteOpen(true)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            {t("actions.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <WorkspaceDeleteAlert
        workspace={workspace}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </>
  );
}
```

- [ ] **Step 3 : Vérifier que la suite des tests existants passe toujours**

```powershell
npm run test:run
```

Expected : tous les tests existants (api, validators, useMe, useWorkspaces, AuthGuard, StatusIndicator, WorkspacesPage, WorkspaceCreateDialog) passent.

- [ ] **Step 4 : Commit**

```powershell
git add frontend/src/pages/WorkspaceActions.tsx frontend/src/pages/WorkspaceDeleteAlert.tsx
git commit -m "feat(M5b): WorkspaceActions dropdown + WorkspaceDeleteAlert (consequences i18n)"
```

---

## Task 17 : `main.tsx` + `App.tsx` + `routes.tsx` + `NotFound.tsx` (wire it all)

**Files:**
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/routes.tsx`
- Create: `frontend/src/pages/NotFound.tsx`

- [ ] **Step 1 : Créer `main.tsx`**

```tsx
// frontend/src/main.tsx
import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import App from "@/App";
import "@/lib/i18n";  // initialize i18next
import "@/styles/globals.css";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      staleTime: 30_000,
      refetchOnWindowFocus: false,
    },
  },
});

const rootElement = document.getElementById("root");
if (!rootElement) throw new Error("Root element #root not found");

ReactDOM.createRoot(rootElement).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/ui">
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </React.StrictMode>,
);
```

- [ ] **Step 2 : Créer `routes.tsx`**

```tsx
// frontend/src/routes.tsx
import { Navigate, Route, Routes } from "react-router-dom";
import { WorkspacesPage } from "@/pages/WorkspacesPage";
import { NotFound } from "@/pages/NotFound";

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<Navigate to="/workspaces" replace />} />
      <Route path="/workspaces" element={<WorkspacesPage />} />
      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
```

- [ ] **Step 3 : Créer `NotFound.tsx`**

```tsx
// frontend/src/pages/NotFound.tsx
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

export function NotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center">
      <h1 className="text-4xl font-bold text-slate-300 mb-2">404</h1>
      <p className="text-slate-600 mb-6">Page introuvable.</p>
      <Button asChild>
        <Link to="/workspaces">Retour aux workspaces</Link>
      </Button>
    </div>
  );
}
```

- [ ] **Step 4 : Créer `App.tsx`**

```tsx
// frontend/src/App.tsx
import { AuthGuard } from "@/components/AuthGuard";
import { Sidebar } from "@/components/Sidebar";
import { Header } from "@/components/Header";
import { Toaster } from "@/components/ui/toaster";
import { AppRoutes } from "@/routes";

function App() {
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
      <Toaster />
    </AuthGuard>
  );
}

export default App;
```

- [ ] **Step 5 : Build test**

```powershell
cd frontend
npm run build
```

Expected : build success, `dist/index.html` + `dist/assets/*` créés. Pas d'erreurs TypeScript.

- [ ] **Step 6 : Vérifier la taille du bundle**

```powershell
ls dist/assets/*.js
```

Cible : bundle JS principal < 500 KB gzipped. Si plus gros, vérifier que tree-shaking fonctionne (imports nommés de lucide-react, pas `import * as`).

- [ ] **Step 7 : Lint + typecheck**

```powershell
npm run lint
npm run typecheck
```

Expected : 0 erreurs.

- [ ] **Step 8 : Run all tests**

```powershell
npm run test:run
```

Expected : tous verts. Cible coverage globale ≥ 80%.

- [ ] **Step 9 : Commit**

```powershell
git add frontend/src/main.tsx frontend/src/App.tsx frontend/src/routes.tsx frontend/src/pages/NotFound.tsx
git commit -m "feat(M5b): wire main.tsx + App layout + routes + 404"
```

---

## Task 18 : Dockerfile + nginx.conf

**Files:**
- Create: `frontend/Dockerfile`
- Create: `frontend/nginx.conf`

- [ ] **Step 1 : Créer `Dockerfile`**

```dockerfile
# frontend/Dockerfile

# Stage 1 : build Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2 : serve via Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html/ui
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
HEALTHCHECK --interval=10s --retries=5 \
  CMD wget -qO- http://localhost:80/healthz || exit 1
```

Note : `COPY --from=builder /app/dist /usr/share/nginx/html/ui` — on copie dans `/ui` sous le root nginx pour matcher le `base: "/ui/"` Vite.

- [ ] **Step 2 : Créer `nginx.conf`**

```nginx
server {
    listen 80;
    server_name _;

    root /usr/share/nginx/html;

    # Assets immutables (hash filenames Vite) : long cache
    location /ui/assets/ {
        expires 1y;
        add_header Cache-Control "public, immutable";
        try_files $uri =404;
    }

    # SPA fallback : toute route /ui/<x> sert /ui/index.html
    location /ui/ {
        try_files $uri /ui/index.html;
    }

    # /ui sans trailing slash → redirect /ui/
    location = /ui {
        return 301 /ui/;
    }

    # Healthcheck Docker
    location = /healthz {
        return 200 "ok\n";
        add_header Content-Type text/plain;
    }
}
```

- [ ] **Step 3 : Test de build local**

```powershell
cd frontend
docker build -t rag-frontend:dev .
```

Expected : build success. Si erreur npm pendant la phase 1, vérifier les versions des deps.

- [ ] **Step 4 : Test de run local (smoke)**

```powershell
docker run --rm -d -p 8080:80 --name rag-frontend-test rag-frontend:dev
curl http://localhost:8080/healthz
curl -I http://localhost:8080/ui/
docker stop rag-frontend-test
```

Expected : `/healthz` → 200 "ok", `/ui/` → 200 avec `text/html`.

- [ ] **Step 5 : Commit**

```powershell
git add frontend/Dockerfile frontend/nginx.conf
git commit -m "feat(M5b): Dockerfile multi-stage (node:20 build → nginx:alpine) + nginx.conf SPA"
```

---

## Task 19 : Caddyfile + docker-compose-dev.yml (wire infra)

**Files:**
- Modify: `Caddyfile`
- Modify: `docker-compose-dev.yml`

- [ ] **Step 1 : Modifier `Caddyfile`**

Remplacer le bloc `handle /ui*` existant et ajouter `/auth/*` + `/me` :

```caddyfile
# Caddyfile dev — reverse proxy HTTP minimal pour LXC 303.
# /api/*  → backend:8000 (FastAPI)
# /auth/* → backend:8000 (OIDC flow)
# /me     → backend:8000 (OIDC)
# /ui*    → frontend:80 (Nginx static, M5b)
# /health → backend:8000 (smoke direct)
# /version → backend:8000 (smoke direct)
# /       → message d'accueil

{
    auto_https off
}

:80 {
    handle /api/* {
        reverse_proxy backend:8000
    }
    handle /auth/* {
        reverse_proxy backend:8000
    }
    handle /me {
        reverse_proxy backend:8000
    }
    handle /health {
        reverse_proxy backend:8000
    }
    handle /version {
        reverse_proxy backend:8000
    }
    handle /ui* {
        reverse_proxy frontend:80
    }
    handle {
        respond "ag-flow.rag — see /ui or /api/*" 200
    }
}
```

- [ ] **Step 2 : Modifier `docker-compose-dev.yml`**

Read d'abord le fichier pour voir l'état actuel, puis ajouter le service `frontend` et update le `depends_on` de Caddy.

Ajouter, après le service `backend` et avant `caddy` :

```yaml
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    image: rag-frontend:latest
    container_name: rag-frontend
    restart: unless-stopped
    networks: [rag]
    healthcheck:
      test: ["CMD", "wget", "-qO-", "http://localhost:80/healthz"]
      interval: 10s
      retries: 5
```

Et update le `caddy` `depends_on` pour inclure `frontend` :
```yaml
  caddy:
    # ... config existante
    depends_on: [backend, frontend]
```

- [ ] **Step 3 : Smoke local — vérifier que le compose se construit**

(Optionnel — peut être skip si tu n'as pas Docker dispo localement.)

```powershell
docker compose -f docker-compose-dev.yml build frontend
```

Expected : build success, image `rag-frontend:latest` créée.

- [ ] **Step 4 : Commit**

```powershell
git add Caddyfile docker-compose-dev.yml
git commit -m "feat(M5b): wire infra (Caddyfile /ui* /auth/* /me + compose frontend service)"
```

---

## Task 20 : Quality gate + smoke deploy LXC 303 + tag m5b-done

**Files:** no code changes (sauf corrections si gates échouent)

- [ ] **Step 1 : Quality gate frontend**

```powershell
cd frontend
npm run lint
npm run typecheck
npm run test:run
npm run build
```

Expected :
- ESLint : 0 erreurs
- TypeScript : 0 erreurs
- Vitest : tous verts, coverage ≥ 80% globale
- Build : success, bundle JS principal < 500 KB gzipped

- [ ] **Step 2 : Quality gate backend (vérifier la non-régression)**

```powershell
cd ..\backend
$env:TEST_POSTGRES_PASSWORD = "i22BfVjVnEG1FhKL0sJ1CuznH73twl1J"
uv run ruff check src tests
uv run mypy src/rag
uv run pytest --tb=no -q
```

Expected : tout vert, ≥ 500 tests passés (≥ 5 nouveaux pour M5b T1).

- [ ] **Step 3 : Commit éventuel des fixes**

```powershell
git add -u
git commit -m "chore(M5b): corrections quality gate (frontend lint/typecheck/coverage)"
```

(Skip si rien à corriger.)

- [ ] **Step 4 : Push la branche**

```powershell
git push origin dev
```

- [ ] **Step 5 : Deploy LXC 303**

```powershell
ssh pve "pct exec 303 -- bash -c 'cd /opt/rag && ./dev-deploy.sh'"
```

Le script va builder le service `frontend` la première fois, ce qui peut prendre 30-60s. Attendre que tous les services soient healthy.

- [ ] **Step 6 : Smoke API + frontend**

```powershell
curl http://192.168.10.184:8000/health
curl http://192.168.10.184:8000/version
curl -I http://192.168.10.184:8000/ui/
curl http://192.168.10.184:8000/ui/index.html | head -20
```

Expected :
- `/health` → `{"status":"ok"}`
- `/version` → SHA = HEAD dev
- `/ui/` → 200 `text/html` (servi par Caddy → frontend:80 → nginx)
- `/ui/index.html` contient `<title>ag-flow.rag</title>` et `<script type="module" src="/ui/assets/...">`

- [ ] **Step 7 : Smoke navigateur (manuel, optionnel)**

Ouvrir http://192.168.10.184:8000/ui dans le navigateur. Attendre :
- Redirect automatique vers `/auth/login` (si pas connecté)
- 503 `oidc_not_configured` (si pas configuré sur LXC 303)

Si tu veux le flow complet : configurer Keycloak via `POST /admin/oidc` avec un realm de test, puis se connecter via le navigateur.

- [ ] **Step 8 : Tag m5b-done**

```powershell
git tag -a m5b-done -m "M5b: Frontend bootstrap + page Workspaces (CRUD complet)"
git push origin m5b-done
```

Expected : `* [new tag] m5b-done -> m5b-done`.

---

## Récapitulatif de couverture (cible)

### Backend (M5b T1)

| Module | Cible |
|---|---|
| `backend/src/rag/auth/bearer.py` (nouvelle fonction) | 100% |
| `backend/src/rag/api/admin.py` (modif) | déjà 100% via integration |

### Frontend

| Module | Cible |
|---|---|
| `frontend/src/lib/api.ts` | 100% |
| `frontend/src/lib/validators.ts` | 100% |
| `frontend/src/hooks/useMe.ts` | ≥ 95% |
| `frontend/src/hooks/useWorkspaces.ts` | ≥ 95% |
| `frontend/src/components/AuthGuard.tsx` | ≥ 90% |
| `frontend/src/components/StatusIndicator.tsx` | 100% |
| `frontend/src/pages/WorkspacesPage.tsx` | ≥ 80% |
| `frontend/src/pages/WorkspaceCreateDialog.tsx` | ≥ 85% |
| **Coverage globale frontend** | ≥ 80% |

Les composants UI shadcn (`src/components/ui/*`) sont exclus du coverage (importés as-is).

## Hors scope (rappel)

- Pages : Sources, Jobs, Models, Push activity, MCP playground (→ M5c-d)
- Page Settings/OIDC config (→ M5e)
- Edition complète d'un workspace (PATCH) — M5b accepte create/delete/rotate/reindex
- Tests E2E Playwright
- Dark mode / theme switcher
- WebSocket / SSE real-time
- Pagination de la table workspaces
