# M5b — Frontend Bootstrap + Page Workspaces : Spec de design

**Date** : 2026-05-16
**Branche** : `dev`
**Pré-requis** : M2 (API admin workspaces), M5a (OIDC backend + `require_oidc_role`).

## 1. Objectif

Second sous-jalon de M5 (IHM web). Pose la fondation frontend complète et
livre **une seule page fonctionnelle** : `Workspaces` (CRUD complet).
Cette page valide toute la pile (Vite, React 18, TS strict, Tailwind,
shadcn/ui, react-router, TanStack Query, i18next, AuthGuard OIDC) en
conditions réelles. Les autres pages (Sources/Jobs/Models/Push/MCP)
arriveront en M5c-d en réutilisant le même pattern.

Le scope strict :
- Bootstrap du projet `frontend/` avec toute la pile listée.
- Container Nginx alpine servant les statics + Caddy reverse proxy `/ui*`.
- Backend : nouvelle dependency `require_master_key_or_oidc_role` qui
  remplace `require_master_key` sur le router admin existant.
- AuthGuard : check `GET /me` → si 401 redirect vers `/auth/login`.
- Layout shell : sidebar light + header user dropdown (logout).
- Page Workspaces : liste (table) + état vide + modal create + alert
  delete + rotate api_key + reindex + toast notifications.
- Tests : Vitest + React Testing Library sur hooks + composants + utils.

Hors scope : Sources/Jobs/Models/Push/MCP (M5c-d), Settings/OIDC config
page (M5e probable), E2E Playwright, dark mode, mobile-first.

## 2. Architecture

```
Navigateur ─────► Caddy:80
                  │
                  ├─ handle /api/*    → backend:8000
                  ├─ handle /auth/*   → backend:8000
                  ├─ handle /me       → backend:8000
                  ├─ handle /health   → backend:8000
                  ├─ handle /version  → backend:8000
                  └─ handle /ui*      → frontend:80 (Nginx)
                                         try_files $uri /ui/index.html

frontend:80 (Nginx alpine)
  Sert /ui/index.html + /ui/assets/*.{js,css}
  SPA fallback : toute route /ui/<x> → index.html

[Flow login]
1. Browser GET /ui/workspaces (sans cookie)
2. SPA → AuthGuard.useMe() → GET /me → 401 oidc_session_missing
3. AuthGuard redirige window.location → /auth/login?next=/ui/workspaces
4. Backend → Keycloak → callback → cookie posé → redirect /ui/workspaces
5. AuthGuard.useMe() → 200 {sub, email, name, roles}
6. Render layout + page Workspaces

[Flow CRUD]
1. User clique "Créer workspace" → modal s'ouvre
2. Submit → POST /api/admin/workspaces (cookie OIDC envoyé automatiquement)
3. Backend dependency : pas de Bearer → check cookie → OIDC verify →
   role rag-admin OK → exécute create_workspace
4. TanStack Query invalide ["workspaces"] → refetch → table mise à jour
5. Toast "Workspace créé"
```

## 3. Décisions de design

| Sujet | Choix | Pourquoi |
|---|---|---|
| **Auth IHM** | Endpoints `/api/admin/*` acceptent EITHER Bearer master-key OR cookie OIDC `rag-admin` | DRY (un seul endpoint au lieu de deux), rétro-compat machines/cURL, frontend appelle juste les endpoints existants avec son cookie. |
| **Static serving** | Container Nginx alpine dédié + Caddy reverse proxy `/ui*` | Séparation backend/frontend, image légère (~25 MB), Nginx natif optimisé pour assets. |
| **Routing UI** | HTML5 history (clean URLs `/ui/workspaces`) | Standard React Router, URLs partageables, SEO-friendly (peu pertinent pour admin, mais clean). |
| **Tests** | Vitest + React Testing Library (hooks + composants critiques + utils) | Couvre la pile sans complexité E2E. Le backend integration tests M5a-T13 couvre déjà le flow OIDC. |
| **Layout** | Sidebar light D1 v2 (fond `zinc-50`, items `slate-900`/600, active `sky-600`/blanc) + header | Validé par maquette browser. Cohérent avec admin SaaS standard (Stripe/Linear-like). |
| **i18n** | i18next + namespace par feature (`common`, `auth`, `nav`, `workspaces`) | Scale propre quand on ajoutera Sources/Jobs/Models. fr/en initial, détection langue navigateur. |
| **State management** | TanStack Query pour server state, useState/useReducer pour UI local | Zéro Redux/Zustand. CLAUDE.md frontend rule : « pas de useEffect + fetch direct ». |
| **Forms** | react-hook-form + Zod resolver | Type-safety bout-en-bout, validation côté client cohérente avec Pydantic backend. |
| **Build** | Vite multi-stage Dockerfile : node:20-alpine build → nginx:alpine serve | Pattern standard. Build reproductible, image finale minimale. |
| **Cookies** | `_oidc_session` et `_oidc_state` signés par Starlette `SessionMiddleware` (M5a) | Hérité de M5a, rien à faire côté frontend. |

## 4. Composants

### 4.1 Backend (modifs ciblées — pas de nouveau module)

| Fichier | Modification |
|---|---|
| `backend/src/rag/auth/bearer.py` | Ajouter factory `require_master_key_or_oidc_role(role)` qui essaie d'abord master-key (si Bearer présent), sinon délègue à `require_oidc_role(role)` |
| `backend/src/rag/api/admin.py` | Remplacer `Depends(require_master_key)` par `Depends(require_master_key_or_oidc_role("rag-admin"))` sur le router admin |
| `backend/src/rag/api/admin_oidc.py` | **Reste master-key only** (un admin OIDC pourrait casser l'OIDC lui-même → lockout) |

### 4.2 Frontend (nouveau projet)

```
frontend/
├── package.json
├── package-lock.json
├── tsconfig.json
├── vite.config.ts
├── tailwind.config.js
├── postcss.config.js
├── index.html
├── Dockerfile
├── nginx.conf
├── .eslintrc.cjs
├── .prettierrc
├── .gitignore
├── vitest.config.ts
├── README.md
└── src/
    ├── main.tsx                 # React root + QueryClientProvider + I18nextProvider + Router
    ├── App.tsx                  # Layout shell + AuthGuard wrapper
    ├── routes.tsx               # Router config (workspaces, login redirect, 404)
    ├── components/
    │   ├── ui/                  # shadcn/ui copy-paste : button, input, label, select,
    │   │                        # dialog, alert-dialog, table, form, toast, dropdown-menu,
    │   │                        # card, badge
    │   ├── AuthGuard.tsx        # Protected route wrapper
    │   ├── Sidebar.tsx          # Nav verticale (D1 v2)
    │   ├── Header.tsx           # Page title + user dropdown
    │   ├── StatusIndicator.tsx  # 🟢🟠🔴 secret status
    │   └── LoadingSpinner.tsx
    ├── pages/
    │   ├── WorkspacesPage.tsx   # Liste + actions
    │   ├── WorkspaceCreateDialog.tsx
    │   ├── WorkspaceDeleteAlert.tsx
    │   ├── WorkspaceActions.tsx # DropdownMenu rotate/reindex/delete
    │   └── NotFound.tsx
    ├── hooks/
    │   ├── useMe.ts             # GET /me, 401 → redirect login
    │   ├── useWorkspaces.ts     # GET/POST/DELETE workspaces
    │   └── useToast.ts          # wrapper shadcn toast
    ├── lib/
    │   ├── api.ts               # fetch wrapper, 401 interceptor, error mapping
    │   ├── i18n.ts              # i18next config
    │   └── validators.ts        # Zod schemas (WorkspaceCreate)
    ├── i18n/
    │   ├── fr/
    │   │   ├── common.json
    │   │   ├── auth.json
    │   │   ├── nav.json
    │   │   └── workspaces.json
    │   └── en/
    │       ├── common.json
    │       ├── auth.json
    │       ├── nav.json
    │       └── workspaces.json
    └── tests/
        ├── components/
        │   ├── AuthGuard.test.tsx
        │   ├── WorkspaceCreateDialog.test.tsx
        │   └── StatusIndicator.test.tsx
        ├── hooks/
        │   ├── useMe.test.ts
        │   └── useWorkspaces.test.ts
        └── lib/
            ├── api.test.ts
            └── validators.test.ts
```

### 4.3 Infra

| Fichier | Modification |
|---|---|
| `docker-compose-dev.yml` | (Re)créer le service `frontend` (build `./frontend`, network `rag`, depends_on backend) |
| `Caddyfile` | Remplacer `handle /ui* { respond 404 }` par `handle /ui* { reverse_proxy frontend:80 }` |
| `frontend/Dockerfile` | Multi-stage : node:20-alpine `npm ci && npm run build` → nginx:alpine serve `/usr/share/nginx/html` |
| `frontend/nginx.conf` | `try_files $uri /ui/index.html` pour SPA fallback ; cache 1y sur `/ui/assets/*` |

## 5. Backend — dependency `require_master_key_or_oidc_role`

```python
# backend/src/rag/auth/bearer.py (ajout)
from typing import Awaitable, Callable

from fastapi import HTTPException, Request
from rag.auth.oidc_dependency import require_oidc_role
from rag.schemas.oidc import OidcUserContext


def require_master_key_or_oidc_role(
    role: str,
) -> Callable[[Request], Awaitable[OidcUserContext | None]]:
    """Dependency : accepte EITHER Bearer master-key OR cookie OIDC role.

    Priorité au Bearer si présent (cas machine/cURL/agents).
    Sinon, délègue à `require_oidc_role(role)` qui check cookie session.
    Si aucun des deux n'est valide → 401.

    Retourne `OidcUserContext` si auth via cookie OIDC, `None` si via
    master-key (cas machine, pas de "user").
    """
    oidc_dep = require_oidc_role(role)

    async def _dep(request: Request) -> OidcUserContext | None:
        auth_header = request.headers.get("Authorization")
        if auth_header:
            require_master_key(request)  # raise 401 si invalid
            return None  # machine, pas de user context
        return await oidc_dep(request)  # raise 401/403/503 selon

    return _dep
```

### Modif sur `api/admin.py`

```python
def build_admin_router() -> APIRouter:
    router = APIRouter(
        tags=["admin"],
        dependencies=[
            Depends(require_master_key_or_oidc_role("rag-admin")),
        ],
    )
    # ... reste inchangé
```

`api/admin_oidc.py` **n'est PAS modifié** — la config OIDC reste master-key only (anti-lockout : si l'admin OIDC casse l'OIDC, plus moyen de se reconnecter).

### Tests backend M5b

`backend/tests/api/test_admin_oidc_auth.py` (nouveau) :

- POST /workspaces avec Bearer master-key → 201 (non-régression)
- POST /workspaces avec cookie OIDC `rag-admin` (mocké via fixtures M5a) → 201
- POST /workspaces avec cookie OIDC `rag-viewer` → 403 `oidc_role_forbidden`
- POST /workspaces sans Bearer ni cookie → 401 `oidc_session_missing`
- POST /admin/oidc avec cookie OIDC admin (sans master-key) → 401 (preuve que admin_oidc reste master-key only)

## 6. Frontend — pile et configuration

### `package.json` dependencies

```json
{
  "dependencies": {
    "react": "^18.3",
    "react-dom": "^18.3",
    "react-router-dom": "^6.27",
    "@tanstack/react-query": "^5.59",
    "i18next": "^23.16",
    "react-i18next": "^15.1",
    "i18next-browser-languagedetector": "^8.0",
    "zod": "^3.23",
    "react-hook-form": "^7.53",
    "@hookform/resolvers": "^3.9",
    "clsx": "^2.1",
    "tailwind-merge": "^2.5",
    "class-variance-authority": "^0.7",
    "lucide-react": "^0.453"
  },
  "devDependencies": {
    "@types/react": "^18.3",
    "@types/react-dom": "^18.3",
    "typescript": "^5.6",
    "vite": "^5.4",
    "@vitejs/plugin-react": "^4.3",
    "tailwindcss": "^3.4",
    "postcss": "^8.4",
    "autoprefixer": "^10.4",
    "vitest": "^2.1",
    "jsdom": "^25.0",
    "@testing-library/react": "^16.0",
    "@testing-library/user-event": "^14.5",
    "@testing-library/jest-dom": "^6.6",
    "eslint": "^9.13",
    "@typescript-eslint/eslint-plugin": "^8.12",
    "@typescript-eslint/parser": "^8.12",
    "eslint-plugin-react-hooks": "^5.0",
    "eslint-plugin-react-refresh": "^0.4",
    "prettier": "^3.3"
  }
}
```

### `tsconfig.json`

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "jsx": "react-jsx",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "noImplicitOverride": true,
    "exactOptionalPropertyTypes": true,
    "verbatimModuleSyntax": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "useDefineForClassFields": true,
    "paths": {
      "@/*": ["./src/*"]
    },
    "baseUrl": "."
  },
  "include": ["src", "vite.config.ts", "vitest.config.ts"]
}
```

### `vite.config.ts`

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
      "/api":   { target: BACKEND, changeOrigin: true },
      "/auth":  { target: BACKEND, changeOrigin: true },
      "/me":    { target: BACKEND, changeOrigin: true },
    },
  },
  build: { outDir: "dist", sourcemap: true },
});
```

### `tailwind.config.js`

```js
/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // Couleur primary alignée sur le mockup D1 v2
        primary: {
          DEFAULT: "#0284c7",  // sky-600
          foreground: "#ffffff",
        },
      },
    },
  },
  plugins: [],
};
```

### Couleurs (sidebar D1 v2 retenu)

| Élément | Token Tailwind | Hex |
|---|---|---|
| Sidebar bg | `zinc-50` | `#fafafa` |
| Brand text | `slate-900` | `#0f172a` |
| Section label | `slate-600` | `#475569` |
| Item normal | `slate-900` + weight 600 | `#0f172a` |
| Item normal icon | `slate-700` | `#334155` |
| Item disabled | `slate-500` + weight 500 | `#64748b` |
| Item disabled icon | `slate-400` | `#94a3b8` |
| Item hover bg | `slate-100` | `#f1f5f9` |
| Item active bg | `sky-600` (primary) | `#0284c7` |
| Item active text | white + weight 700 | `#ffffff` |
| Item active icon | white | `#ffffff` |

## 7. Layout shell

```tsx
// src/App.tsx (schéma)
function App() {
  return (
    <BrowserRouter basename="/ui">
      <AuthGuard>
        <div className="flex h-screen bg-slate-50">
          <Sidebar />
          <div className="flex-1 flex flex-col">
            <Header />
            <main className="flex-1 overflow-y-auto p-6">
              <Routes>
                <Route path="/" element={<Navigate to="/workspaces" replace />} />
                <Route path="/workspaces" element={<WorkspacesPage />} />
                <Route path="*" element={<NotFound />} />
              </Routes>
            </main>
          </div>
        </div>
      </AuthGuard>
    </BrowserRouter>
  );
}
```

### `AuthGuard`

```tsx
function AuthGuard({ children }: { children: ReactNode }) {
  const { data, error, isLoading } = useMe();

  if (isLoading) return <LoadingSpinner />;

  if (error && isUnauthorized(error)) {
    const next = window.location.pathname + window.location.search;
    window.location.href = `/auth/login?next=${encodeURIComponent(next)}`;
    return null;
  }

  if (!data) return <ErrorScreen />;

  return <UserContext.Provider value={data}>{children}</UserContext.Provider>;
}
```

### `useMe` hook

```ts
function useMe() {
  return useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const resp = await fetch("/me", { credentials: "include" });
      if (resp.status === 401) {
        const err = new Error("unauthorized") as Error & { status: number };
        err.status = 401;
        throw err;
      }
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      return (await resp.json()) as MeResponse;
    },
    retry: false,  // ne pas retry sur 401
    staleTime: 5 * 60 * 1000,
  });
}
```

## 8. Page Workspaces — composition

### `WorkspacesPage.tsx`

```tsx
function WorkspacesPage() {
  const { t } = useTranslation("workspaces");
  const { data, isLoading } = useWorkspaces();
  const [createOpen, setCreateOpen] = useState(false);

  if (isLoading) return <LoadingSpinner />;

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center">
        <h2 className="text-xl font-semibold">{t("title")}</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="w-4 h-4 mr-1" /> {t("create")}
        </Button>
      </div>

      {data?.length === 0 ? (
        <EmptyState onCreate={() => setCreateOpen(true)} />
      ) : (
        <WorkspacesTable workspaces={data ?? []} />
      )}

      <WorkspaceCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
```

### `WorkspacesTable.tsx`

```tsx
function WorkspacesTable({ workspaces }: { workspaces: Workspace[] }) {
  const { t } = useTranslation("workspaces");

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>{t("table.name")}</TableHead>
          <TableHead>{t("table.indexer")}</TableHead>
          <TableHead>{t("table.sources")}</TableHead>
          <TableHead>{t("table.documents")}</TableHead>
          <TableHead>{t("table.last_indexed")}</TableHead>
          <TableHead className="text-right" />
        </TableRow>
      </TableHeader>
      <TableBody>
        {workspaces.map((ws) => (
          <TableRow key={ws.id}>
            <TableCell className="font-medium">{ws.name}</TableCell>
            <TableCell>
              <Badge variant="outline">
                {ws.indexer.provider}/{ws.indexer.model}
              </Badge>
            </TableCell>
            <TableCell>{ws.sources_count}</TableCell>
            <TableCell>{ws.documents_count}</TableCell>
            <TableCell className="text-muted-foreground">
              {formatRelative(ws.last_indexed_at)}
            </TableCell>
            <TableCell className="text-right">
              <WorkspaceActions workspace={ws} />
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

### Hooks TanStack Query

```ts
// src/hooks/useWorkspaces.ts
export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => api.get<Workspace[]>("/api/admin/workspaces"),
  });
}

export function useCreateWorkspace() {
  const qc = useQueryClient();
  const { toast } = useToast();
  return useMutation({
    mutationFn: (payload: WorkspaceCreate) =>
      api.post<WorkspaceCreateResponse>("/api/admin/workspaces", payload),
    onSuccess: (resp) => {
      qc.invalidateQueries({ queryKey: ["workspaces"] });
      toast.success({ title: t("workspaces:created", { name: resp.name }) });
    },
    onError: (err) => toast.error({ title: mapApiError(err) }),
  });
}

export function useDeleteWorkspace() { /* DELETE /api/admin/workspaces/{name} */ }
export function useRotateApiKey()    { /* POST   /api/admin/workspaces/{name}/rotate-apikey */ }
export function useReindex()         { /* POST   /api/admin/workspaces/{name}/reindex?confirm=true */ }
```

### Form Zod validator

```ts
// src/lib/validators.ts
export const workspaceCreateSchema = z.object({
  name: z.string()
    .min(1)
    .max(64)
    .regex(/^[a-z][a-z0-9_-]{0,62}$/, "Lettres minuscules, chiffres, _ ou -"),
  indexer: z.object({
    provider: z.enum(["openai", "voyage", "ollama"]),
    model: z.string().min(1),
    api_key_ref: z.string().optional(),
    base_url: z.string().url().optional(),
  }).refine(
    (v) => v.provider === "ollama" || !!v.api_key_ref,
    { message: "api_key_ref requis pour openai/voyage", path: ["api_key_ref"] }
  ),
});
```

## 9. Mockups validés (D1 v2)

### Écran 1 — Vue d'ensemble (table avec données)

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ag-flow.rag       │ Workspaces                          BB black.beard@... ▾│
├───────────────────┤                                                        │
│                   │                                                        │
│  ADMINISTRATION   │  [+ Créer un workspace]                                │
│                   │                                                        │
│ ▣ Workspaces ●●●  │  ┌──────────────┬────────────────┬─────┬──────┬──────┐│
│ ≡ Sources (gris)  │  │ Nom          │ Indexer        │Srcs │ Docs │ ⋮   ││
│ ◷ Jobs (gris)     │  ├──────────────┼────────────────┼─────┼──────┼──────┤│
│ ▤ Modèles (gris)  │  │ harpocrate   │ openai/3-small │  3  │ 412  │ ⋮   ││
│                   │  │ ag-flow-docker│voyage/3-lite  │  1  │  89  │ ⋮   ││
│  USAGE            │  │ colis21      │ ollama/mxbai   │  2  │1245  │ ⋮   ││
│ ↗ Push (gris)     │  └──────────────┴────────────────┴─────┴──────┴──────┘│
│ ⌕ MCP (gris)      │                                                        │
└───────────────────┴────────────────────────────────────────────────────────┘
```

### Écran 2 — État vide

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ag-flow.rag       │ Workspaces                          BB black.beard@... ▾│
├───────────────────┤                                                        │
│                   │              ┌─────────────────────────┐               │
│  ADMINISTRATION   │              │           📁            │               │
│                   │              │   Aucun workspace       │               │
│ ▣ Workspaces      │              │                         │               │
│ ≡ Sources         │              │   Créez votre premier   │               │
│ ◷ Jobs            │              │   workspace pour        │               │
│ ▤ Modèles         │              │   commencer à indexer   │               │
│                   │              │                         │               │
│  USAGE            │              │  [+ Créer un workspace] │               │
│ ↗ Push            │              └─────────────────────────┘               │
│ ⌕ MCP             │                                                        │
└───────────────────┴────────────────────────────────────────────────────────┘
```

### Écran 3 — Modal Créer

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ag-flow.rag       │ Workspaces                          BB black.beard@... ▾│
├───────────────────┤                                                        │
│  (sidebar grisée) │   ┌──────────────────────────────────────┐             │
│                   │   │  Créer un workspace             ✕    │             │
│                   │   ├──────────────────────────────────────┤             │
│                   │   │  NOM *                               │             │
│                   │   │  [ harpocrate                      ] │             │
│                   │   │  Lettres minuscules, chiffres, _ - │             │
│                   │   │                                      │             │
│                   │   │  ─── INDEXER ─────────────────────  │             │
│                   │   │                                      │             │
│                   │   │  PROVIDER *      MODÈLE *           │             │
│                   │   │  [ openai  ▾]    [ text-embed... ▾] │             │
│                   │   │                                      │             │
│                   │   │  RÉFÉRENCE CLÉ API (VAULT)          │             │
│                   │   │  [ openai_embedding_key            ] │             │
│                   │   │  🟢 Clé présente dans Harpocrate    │             │
│                   │   │                                      │             │
│                   │   │  BASE URL (optionnel - Ollama)       │             │
│                   │   │  [                                 ] │             │
│                   │   ├──────────────────────────────────────┤             │
│                   │   │              [Annuler]  [Créer]      │             │
│                   │   └──────────────────────────────────────┘             │
└───────────────────┴────────────────────────────────────────────────────────┘
```

### Écran 4 — Confirm delete

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ag-flow.rag       │ Workspaces                          BB black.beard@... ▾│
├───────────────────┤                                                        │
│  (sidebar grisée) │      ┌───────────────────────────────────┐             │
│                   │      │ ⚠  Supprimer `harpocrate` ?       │             │
│                   │      ├───────────────────────────────────┤             │
│                   │      │ Cette action est irréversible :   │             │
│                   │      │                                   │             │
│                   │      │ • La base pgvector                │             │
│                   │      │   rag_harpocrate sera droppée     │             │
│                   │      │ • Les 412 documents indexés       │             │
│                   │      │   seront perdus                   │             │
│                   │      │ • L'api_key sera révoquée         │             │
│                   │      │   immédiatement                   │             │
│                   │      │ • Les agents utilisant cette      │             │
│                   │      │   api_key recevront 401           │             │
│                   │      ├───────────────────────────────────┤             │
│                   │      │  [Annuler] [Supprimer définitiv.]│             │
│                   │      └───────────────────────────────────┘             │
└───────────────────┴────────────────────────────────────────────────────────┘
```

### Écran 5 — Toast + dropdown row actions

```
┌────────────────────────────────────────────────────────────────────────────┐
│ ag-flow.rag       │ Workspaces                          BB black.beard@... ▾│
├───────────────────┤                                                        │
│                   │  [+ Créer un workspace]                                │
│  ADMINISTRATION   │                                                        │
│                   │  ┌──────────────┬────────────────┬─────┬──────┬─────┐ │
│ ▣ Workspaces ●●●  │  │ Nom          │ Indexer        │Srcs │ Docs │ ⋮   │ │
│ ≡ Sources         │  ├──────────────┼────────────────┼─────┼──────┼─────┤ │
│ ◷ Jobs            │  │ harpocrate   │ openai/3-small │  3  │ 412  │ ⋮   │ │
│                   │  │ ag-flow-docker│voyage/3-lite  │  1  │  89  │ ⋮(*)│ │
│  USAGE            │  └──────────────┴────────────────┴─────┴──────┴─────┘ │
│                   │                                  ┌──────────────────┐ │
│                   │                                  │ 🔄 Régénérer key │ │
│                   │  ┌─────────────────────────────┐ │ ↻  Réindexer     │ │
│                   │  │ ✓ Workspace harpocrate créé │ │ ──────────────── │ │
│                   │  └─────────────────────────────┘ │ 🗑  Supprimer    │ │
│                   │   (toast 4s auto-dismiss)        └──────────────────┘ │
└───────────────────┴────────────────────────────────────────────────────────┘
```

## 10. Matrice d'erreurs (UX côté frontend)

| Code API | Comportement UX | Source |
|---|---|---|
| **401 oidc_session_missing** | Redirect `window.location = /auth/login?next=<current>` | `AuthGuard` ou api interceptor |
| **401 oidc_session_expired** | `POST /auth/refresh` → si OK retry, sinon redirect login | api interceptor |
| **403 oidc_role_forbidden** | Toast "Permissions insuffisantes — contactez un admin" | Toast layer |
| **404 workspace_not_found** | Toast erreur + invalidate query | Mutation onError |
| **409 workspace_already_exists** | Erreur inline sur champ `name` du form | Form errors |
| **422 (Pydantic)** | Mapping `errors[].loc → field` puis erreurs inline | Form errors |
| **502 embedding_provider_error** | Toast warning "Provider d'embedding indisponible" | Toast layer |
| **503 oidc_not_configured** | Page d'erreur "L'admin doit configurer OIDC : POST /admin/oidc" | AuthGuard catch |
| **500 / autre** | Toast "Erreur serveur, réessayer" | Toast layer |

## 11. Tests frontend (Vitest + RTL)

### Couverture cible

| Module | Cible |
|---|---|
| `hooks/useMe.ts` | ≥ 95% (login redirect, success, 401) |
| `hooks/useWorkspaces.ts` | ≥ 95% (list, create, delete, rotate, reindex + invalidation) |
| `lib/api.ts` | 100% (401 interceptor, error mapping) |
| `lib/validators.ts` | 100% (Zod schemas) |
| `components/AuthGuard.tsx` | ≥ 90% |
| `components/WorkspaceCreateDialog.tsx` | ≥ 85% (form submit, validation, conditional Ollama base_url) |
| `components/WorkspacesTable.tsx` | ≥ 80% (render, empty, click ⋮) |
| **Couverture globale frontend** | ≥ 80% |

### Pattern Vitest (convention CLAUDE.md)

```ts
// src/tests/hooks/useWorkspaces.test.ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import * as api from "@/lib/api";

describe("useWorkspaces", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fetches workspaces list and returns data", async () => {
    vi.spyOn(api, "get").mockResolvedValue([
      { id: "1", name: "harpocrate", /* ... */ },
    ]);

    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const wrapper = ({ children }: { children: ReactNode }) => (
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    );

    const { result } = renderHook(() => useWorkspaces(), { wrapper });
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toHaveLength(1);
  });
});
```

CLAUDE.md frontend rules : `describe`/`it`, pas `test`.

## 12. Build + déploiement

### `frontend/Dockerfile` (multi-stage)

```dockerfile
# Stage 1 : build Vite
FROM node:20-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build  # → /app/dist

# Stage 2 : serve via Nginx
FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

### `frontend/nginx.conf`

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

    # SPA fallback : toute route /ui/<x> sert index.html
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

### `Caddyfile` (mise à jour)

```caddyfile
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

### `docker-compose-dev.yml` (ajout service frontend)

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

  caddy:
    # ... config existante
    depends_on: [backend, frontend]
```

## 13. Hors scope M5b (rappel)

- Pages : Sources, Jobs, Models, Push activity, MCP playground (→ M5c-d)
- Page Settings/OIDC config dans l'IHM (→ M5e — gestion des secrets en DB)
- Edition complète d'un workspace (PATCH) — M5b accepte uniquement Create + Delete + Rotate api_key + Reindex
- Tests E2E Playwright contre vrai Keycloak (→ M5c+ si nécessaire)
- Dark mode / theme switcher
- Animations Framer Motion
- WebSocket / SSE pour real-time jobs (→ M5c)
- Mobile-first design (responsive basique suffit)
- Pagination de la table workspaces (en MVP : afficher tous ; si > 100 workspaces un jour, paginer)

## 14. Risques connus

| Risque | Mitigation |
|---|---|
| Cookie `_oidc_session` pas envoyé en dev (cross-origin localhost:5173 → backend LXC) | Proxy Vite `/api`+`/auth`+`/me` → backend, donc même origin du point de vue navigateur. `credentials: "include"` côté fetch. |
| Cache Nginx `/ui/assets/*` rend les déploys cassés si filenames non hashed | Vite hash les filenames (`index-abc123.js`) par défaut. `expires 1y` safe. `index.html` n'est PAS caché. |
| SPA fallback Nginx renvoie `/ui/index.html` pour `/ui/api/...` 404 | Caddy attrape `/api/*` AVANT `/ui*`. React Router ne route pas vers `/api`. Pas de risque concret. |
| TypeScript strict + react-hook-form types complexes | `@hookform/resolvers/zod` infère les types automatiquement depuis le schema Zod. Boilerplate minimal. |
| Build size > 1 MB | Tailwind purge + Vite tree-shaking + lucide-react imports nommés. Cible : < 500 KB gzipped. À mesurer post-build. |
| Cookies non sécurisés en dev local HTTP | `https_only=False` en environment=dev (déjà configuré M5a). |
| Première deploy après M5b : Caddy attend `frontend:80` qui n'existait pas | Le service est ajouté dans le compose, `dev-deploy.sh` fait `docker compose up -d --build` qui build le service frontend en même temps. Caddy `depends_on: [frontend]` garantit l'ordre. |
| Master-key + cookie OIDC envoyés simultanément | La dependency prend Bearer en priorité. Le frontend n'envoie jamais de Bearer (cookie seulement). Cas théorique non rencontré. |
| `require_master_key_or_oidc_role` casse les tests existants utilisant master-key | Non — le flow Bearer reste identique, c'est juste un wrap autour de `require_master_key`. Tests M2/M4 non régressifs. |

## 15. Risques d'infrastructure et déploiement

| Risque | Mitigation |
|---|---|
| Le LXC 303 n'a pas accès au Keycloak homelab (réseau) | Le flow OIDC nécessite que LXC 303 résolve `keycloak.yoops.org`. Doit être validé avant le smoke deploy. |
| Cookie SameSite=Lax bloque redirect cross-site Keycloak → callback | SameSite=Lax permet le navigateur de renvoyer le cookie sur top-level navigations (redirect 302 après login). C'est OK. |
| Caddy strip-prefix ou non sur `/ui*` | On NE strip PAS le préfixe. Vite `base: "/ui/"` émet des chemins absolus avec `/ui/`. Nginx serve depuis `root /usr/share/nginx/html` avec les fichiers `dist/index.html` qui référencent `/ui/assets/...`. Cohérent. |
