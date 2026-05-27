# M7b — Page Config OIDC admin Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer la page `/settings/oidc-config` permettant à un admin (master_key OU OIDC role rag-admin) de configurer le SSO via formulaire, et corriger l'incohérence d'auth backend qui empêche aujourd'hui les appels OIDC sur les endpoints `/api/admin/oidc`.

**Architecture:** Backend : remplace `require_master_key` par `require_master_key_or_oidc_role("rag-admin")` dans `admin_oidc.py`. Frontend : page simple form (3 champs Zod) en mode upsert silencieux (GET → si data pré-remplit, si 503 form vide). Pattern aligné M7a (page simple) + M6 (form react-hook-form + Zod + toast).

**Tech Stack:** Python 3.12 + FastAPI + pytest (backend). React 18 + TS strict + TanStack Query + react-hook-form + Zod + shadcn/ui Dialog/Input/Button + i18next (frontend).

**Spec design** : `docs/superpowers/specs/2026-05-17-M7b-frontend-oidc-config-design.md`

**Note importante** : la spec design dit que GET retourne 404 si non configuré. **La réalité backend est 503** (cf. `test_admin_oidc.py:21` qui vérifie `status_code == 503`). Le plan utilise donc **503** comme code de "pas encore configuré" à intercepter côté frontend.

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `backend/src/rag/api/admin_oidc.py` | **Modify** | `require_master_key` → `require_master_key_or_oidc_role("rag-admin")` |
| `backend/tests/api/test_admin_oidc_auth.py:201` | **Modify** | Adapter le test qui assert encore `still_requires_master_key` |
| `backend/tests/api/test_admin_oidc.py` | **Modify** | Ajout tests OIDC role (post + get) |
| `frontend/src/lib/oidc-config.types.ts` | **Create** | Types TS (OidcConfig, OidcConfigCreate) |
| `frontend/src/lib/oidc-config.ts` | **Create** | API client (2 méthodes) |
| `frontend/src/hooks/useOidcConfig.ts` | **Create** | 1 query (gère 503 → null) + 1 mutation |
| `frontend/src/pages/OidcConfigPage.tsx` | **Create** | Form complet upsert |
| `frontend/src/components/Sidebar.tsx` | **Modify** | +item « Config OIDC » sous Configuration |
| `frontend/src/routes.tsx` | **Modify** | +Route `/settings/oidc-config` |
| `frontend/src/i18n/fr/oidc.json` | **Create** | Labels FR |
| `frontend/src/i18n/en/oidc.json` | **Create** | Labels EN |
| `frontend/src/lib/i18n.ts` | **Modify** | Enregistrer namespace `oidc` |
| `frontend/src/i18n/fr/nav.json` | **Modify** | +clé `items.oidc_config` |
| `frontend/src/i18n/en/nav.json` | **Modify** | idem |
| `frontend/src/pages/__tests__/OidcConfigPage.test.tsx` | **Create** | Tests Vitest |

---

## Task 1: Backend — fix dépendance auth admin_oidc + tests

**Files:**
- Modify: `backend/src/rag/api/admin_oidc.py`
- Modify: `backend/tests/api/test_admin_oidc_auth.py`
- Modify: `backend/tests/api/test_admin_oidc.py`

- [ ] **Step 1: Modifier `admin_oidc.py`**

Lire `backend/src/rag/api/admin_oidc.py` et appliquer :

```python
# Ligne 6 — import :
from rag.auth.bearer import require_master_key_or_oidc_role

# Ligne 14 — dépendances :
dependencies=[Depends(require_master_key_or_oidc_role("rag-admin"))],
```

Retirer l'import désormais inutile de `require_master_key`.

- [ ] **Step 2: Adapter le test `test_admin_oidc_endpoint_still_requires_master_key`**

Lire `backend/tests/api/test_admin_oidc_auth.py` autour de la ligne 201. Le test actuel attendait 401 sur `/api/admin/oidc` avec session OIDC seule (le name `still_requires_master_key` reflète l'ancienne contrainte).

Renommer et inverser l'assertion. Nouveau nom : `test_admin_oidc_endpoint_accepts_oidc_admin_role`. Adapter le corps pour vérifier 200/201 quand la session OIDC porte le rôle `rag-admin`.

Si tu n'es pas sûr du contenu exact, lis le test existant en entier d'abord. Modifie en gardant le même pattern que `test_post_workspaces_with_oidc_admin_role_succeeds` (lignes 144-163 du même fichier).

- [ ] **Step 3: Ajouter test OIDC sans rôle pour `/oidc`**

Dans `test_admin_oidc_auth.py`, ajouter un nouveau test symétrique à `test_post_workspaces_with_oidc_viewer_role_returns_403` mais pour `POST /api/admin/oidc` :

```python
def test_post_oidc_with_oidc_viewer_role_returns_403(
    admin_client: TestClient,
    oidc_viewer_session_cookie: str,  # adapter selon fixture existante
) -> None:
    r = admin_client.post(
        "/api/admin/oidc",
        cookies={"session": oidc_viewer_session_cookie},
        json={
            "issuer": "https://keycloak.example.com/realms/test",
            "client_id": "rag",
            "client_secret_ref": "kc_rag_secret",
        },
    )
    assert r.status_code == 403
```

Adapte le nom de la fixture cookie selon ce qui existe dans `tests/api/conftest.py`.

- [ ] **Step 4: Lancer tests OIDC**

Récupérer le password Postgres du LXC test si nécessaire :

```bash
ssh pve "pct exec 401 -- bash -c 'cat /opt/rag/.env 2>/dev/null | grep ^POSTGRES_PASSWORD'"
```

Si CTID 401 n'existe plus, créer un LXC test : `./scripts/run-test.sh` (CLEANUP=0).

Lancer :

```bash
cd backend
RAG_POSTGRES_URL=postgresql://rag:<pw>@<lxc-ip>:5432/rag_config \
RAG_POSTGRES_ADMIN_URL=postgresql://rag:<pw>@<lxc-ip>:5432/postgres \
RAG_API_KEY_DEK=$(python -c "print('x' * 32)") \
RAG_MASTER_KEY=$(python -c "print('m' * 32)") \
RAG_PUBLIC_URL=http://localhost:8000 \
uv run pytest tests/api/test_admin_oidc.py tests/api/test_admin_oidc_auth.py -v
```

Expected : tous PASS (les anciens + le nouveau).

- [ ] **Step 5: Commit**

```bash
git add backend/src/rag/api/admin_oidc.py \
        backend/tests/api/test_admin_oidc_auth.py \
        backend/tests/api/test_admin_oidc.py
git commit -m "feat(M7b-T1): admin_oidc accepte OIDC role rag-admin (était master_key seule)"
```

---

## Task 2: Frontend — Types TS + API client + hooks

**Files:**
- Create: `frontend/src/lib/oidc-config.types.ts`
- Create: `frontend/src/lib/oidc-config.ts`
- Create: `frontend/src/hooks/useOidcConfig.ts`

- [ ] **Step 1: Créer `lib/oidc-config.types.ts`**

```typescript
// Types miroirs des schemas Pydantic OidcConfigRead / OidcConfigCreate
// (cf. backend/src/rag/schemas/oidc.py)

export type OidcConfig = {
  issuer: string;
  client_id: string;
  client_secret_ref: string;
};

export type OidcConfigCreate = {
  issuer: string;
  client_id: string;
  client_secret_ref: string;
};
```

- [ ] **Step 2: Créer `lib/oidc-config.ts`**

```typescript
import { api } from "@/lib/api";
import type { OidcConfig, OidcConfigCreate } from "@/lib/oidc-config.types";

const BASE = "/api/admin/oidc";

export const oidcConfigApi = {
  get: () => api.get<OidcConfig>(BASE),
  upsert: (payload: OidcConfigCreate) =>
    api.post<OidcConfig>(BASE, payload),
};
```

- [ ] **Step 3: Créer `hooks/useOidcConfig.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { oidcConfigApi } from "@/lib/oidc-config";
import type { OidcConfig, OidcConfigCreate } from "@/lib/oidc-config.types";

/**
 * Récupère la config OIDC.
 * Backend renvoie 503 quand non configurée (cf. test_admin_oidc.py:21) — on
 * intercepte ce cas et retourne `null` pour permettre au composant d'afficher
 * un form vide.
 */
export function useOidcConfig() {
  return useQuery<OidcConfig | null>({
    queryKey: ["oidc-config"],
    queryFn: async () => {
      try {
        return await oidcConfigApi.get();
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          return null;
        }
        throw err;
      }
    },
  });
}

export function useUpsertOidcConfig() {
  const qc = useQueryClient();
  return useMutation<OidcConfig, Error, OidcConfigCreate>({
    mutationFn: (payload) => oidcConfigApi.upsert(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["oidc-config"] });
    },
  });
}
```

- [ ] **Step 4: Smoke**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```
Expected : 0 erreur.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/oidc-config.types.ts \
        frontend/src/lib/oidc-config.ts \
        frontend/src/hooks/useOidcConfig.ts
git commit -m "feat(M7b-T2): types TS + API client + hooks oidc-config"
```

---

## Task 3: Sidebar +item + route + page squelette

**Files:**
- Modify: `frontend/src/components/Sidebar.tsx`
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/i18n/fr/nav.json`
- Modify: `frontend/src/i18n/en/nav.json`
- Create: `frontend/src/pages/OidcConfigPage.tsx`

- [ ] **Step 1: Modifier `Sidebar.tsx`**

Repérer le bloc Configuration (`{t("sections.configuration")}` autour de la ligne 84). Sous l'item « Coffres Harpocrate » existant, ajouter :

```tsx
<NavItem
  to="/settings/oidc-config"
  icon={<KeyRound />}
  label={t("items.oidc_config")}
/>
```

Ajouter `KeyRound` dans l'import lucide-react en haut du fichier (à la ligne 5-7 où les autres icônes sont importées).

- [ ] **Step 2: Modifier `routes.tsx`**

Ajouter :

```tsx
import { OidcConfigPage } from "@/pages/OidcConfigPage";
// ...
<Route path="/settings/oidc-config" element={<OidcConfigPage />} />
```

Place la route à côté de `/settings/harpocrate-vaults` (pattern de la section Configuration). Toutes les routes sont déjà sous AuthGuard via `App.tsx`.

- [ ] **Step 3: Ajouter la clé i18n nav FR**

Lire `frontend/src/i18n/fr/nav.json` et ajouter dans la section `items` :

```json
"oidc_config": "Config OIDC"
```

- [ ] **Step 4: Ajouter la clé i18n nav EN**

Lire `frontend/src/i18n/en/nav.json` et ajouter :

```json
"oidc_config": "OIDC config"
```

- [ ] **Step 5: Créer `OidcConfigPage.tsx` (stub)**

```tsx
import { useTranslation } from "react-i18next";

export function OidcConfigPage() {
  const { t } = useTranslation("oidc");
  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>
      <div className="mt-6 text-slate-500">Form (T4)</div>
    </div>
  );
}
```

Le namespace `oidc` n'existe pas encore (T5), `t()` renverra les clés brutes — toléré.

- [ ] **Step 6: Smoke**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Vérifier en dev si possible : `/settings/oidc-config` est cliquable depuis la sidebar.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/Sidebar.tsx \
        frontend/src/routes.tsx \
        frontend/src/i18n/fr/nav.json \
        frontend/src/i18n/en/nav.json \
        frontend/src/pages/OidcConfigPage.tsx
git commit -m "feat(M7b-T3): sidebar +item Config OIDC + route + page stub"
```

---

## Task 4: Form complet (Zod + GET/POST + Save/Cancel + warning)

**Files:**
- Rewrite: `frontend/src/pages/OidcConfigPage.tsx`

- [ ] **Step 1: Implémenter `OidcConfigPage.tsx`**

```tsx
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useOidcConfig, useUpsertOidcConfig } from "@/hooks/useOidcConfig";
import { useToast } from "@/hooks/useToast";

const schema = z.object({
  issuer: z.string().url("invalid_url"),
  client_id: z.string().min(1, "required").max(255, "too_long"),
  client_secret_ref: z.string()
    .min(1, "required")
    .max(255, "too_long")
    .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only"),
});

type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = { issuer: "", client_id: "", client_secret_ref: "" };

export function OidcConfigPage() {
  const { t } = useTranslation("oidc");
  const { toast } = useToast();
  const { data, isLoading } = useOidcConfig();
  const upsert = useUpsertOidcConfig();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });

  // Synchronise le form quand les données serveur arrivent / changent.
  useEffect(() => {
    if (isLoading) return;
    form.reset(data ?? EMPTY);
  }, [data, isLoading, form]);

  const onSubmit = (values: FormValues) => {
    upsert.mutate(values, {
      onSuccess: (saved) => {
        toast({ title: t("save.success") });
        form.reset(saved);
      },
      onError: () => toast({ title: t("save.error"), variant: "destructive" }),
    });
  };

  const handleCancel = () => {
    form.reset(data ?? EMPTY);
  };

  if (isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingSpinner /></div>;
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>

      <form onSubmit={form.handleSubmit(onSubmit)} className="mt-6 space-y-4 rounded-md border bg-white p-6">
        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.issuer")}</label>
          <Input
            {...form.register("issuer")}
            placeholder="https://keycloak.example.com/realms/yoops"
            className="mt-1"
          />
          {form.formState.errors.issuer && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.issuer.message}`)}
            </p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.client_id")}</label>
          <Input {...form.register("client_id")} placeholder="rag" className="mt-1" />
          {form.formState.errors.client_id && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.client_id.message}`)}
            </p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">{t("fields.client_secret_ref")}</label>
          <Input
            {...form.register("client_secret_ref")}
            placeholder="keycloak_rag_client_secret"
            className="mt-1 font-mono"
          />
          {form.formState.errors.client_secret_ref && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.client_secret_ref.message}`)}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button type="button" variant="ghost" onClick={handleCancel} disabled={!form.formState.isDirty}>
            {t("actions.cancel")}
          </Button>
          <Button type="submit" disabled={!form.formState.isDirty || upsert.isPending}>
            {t("actions.save")}
          </Button>
        </div>
      </form>

      <div className="mt-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-amber-900">{t("warning.sessions")}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

Vérifier en dev si possible : page `/settings/oidc-config` charge, form vide ou pré-rempli selon état BDD.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/OidcConfigPage.tsx
git commit -m "feat(M7b-T4): OidcConfigPage form complet (upsert + Zod + Save/Cancel)"
```

---

## Task 5: i18n FR+EN + tests Vitest + audit strings

**Files:**
- Create: `frontend/src/i18n/fr/oidc.json`
- Create: `frontend/src/i18n/en/oidc.json`
- Modify: `frontend/src/lib/i18n.ts`
- Create: `frontend/src/pages/__tests__/OidcConfigPage.test.tsx`

- [ ] **Step 1: Créer `frontend/src/i18n/fr/oidc.json`**

```json
{
  "title": "Configuration OIDC",
  "subtitle": "Authentification Single Sign-On (Keycloak, Auth0, …).",
  "fields": {
    "issuer": "Issuer URL",
    "client_id": "Client ID",
    "client_secret_ref": "Référence client_secret (Harpocrate)"
  },
  "actions": {
    "cancel": "Annuler",
    "save": "Enregistrer"
  },
  "save": {
    "success": "Configuration OIDC enregistrée.",
    "error": "Échec de l'enregistrement."
  },
  "warning": {
    "sessions": "Modifier l'OIDC déconnecte les sessions actives."
  },
  "errors": {
    "invalid_url": "URL invalide.",
    "required": "Champ requis.",
    "too_long": "Maximum 255 caractères.",
    "alphanum_underscore_only": "Caractères autorisés : a-z, A-Z, 0-9, underscore."
  }
}
```

- [ ] **Step 2: Créer `frontend/src/i18n/en/oidc.json`**

```json
{
  "title": "OIDC configuration",
  "subtitle": "Single Sign-On authentication (Keycloak, Auth0, …).",
  "fields": {
    "issuer": "Issuer URL",
    "client_id": "Client ID",
    "client_secret_ref": "client_secret reference (Harpocrate)"
  },
  "actions": {
    "cancel": "Cancel",
    "save": "Save"
  },
  "save": {
    "success": "OIDC configuration saved.",
    "error": "Failed to save."
  },
  "warning": {
    "sessions": "Changing OIDC disconnects active sessions."
  },
  "errors": {
    "invalid_url": "Invalid URL.",
    "required": "Required field.",
    "too_long": "Maximum 255 characters.",
    "alphanum_underscore_only": "Allowed characters: a-z, A-Z, 0-9, underscore."
  }
}
```

- [ ] **Step 3: Modifier `frontend/src/lib/i18n.ts`**

Lire le fichier, identifier les imports et `resources` existants (pattern pour `workspace`, `models`, etc.). Ajouter :

```typescript
import oidcFr from "@/i18n/fr/oidc.json";
import oidcEn from "@/i18n/en/oidc.json";
// ...
// dans resources :
//   fr: { ..., oidc: oidcFr }
//   en: { ..., oidc: oidcEn }
// dans ns array : "oidc"
```

Adapter selon la structure réelle du fichier.

- [ ] **Step 4: Audit strings hardcoded**

```bash
cd frontend
grep -nE '>[A-Za-zÀ-ÿ ]{3,}<' src/pages/OidcConfigPage.tsx
```

Examiner chaque match. Toute string humaine doit passer par `t()`. Les placeholders dans `<Input placeholder="...">` (`"https://keycloak.example.com/realms/yoops"`, `"rag"`, `"keycloak_rag_client_secret"`) sont des **exemples techniques**, pas du texte affiché à traduire — on les garde en hardcoded ou on les passe par `t("fields.*.placeholder")` selon préférence. **Choix M7b** : les garder en hardcoded (valeurs techniques universelles, pas traduisibles).

- [ ] **Step 5: Créer le test Vitest**

`frontend/src/pages/__tests__/OidcConfigPage.test.tsx` :

```tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "@/lib/i18n";
import { OidcConfigPage } from "@/pages/OidcConfigPage";

const mutateMock = vi.fn();

vi.mock("@/hooks/useOidcConfig", () => ({
  useOidcConfig: vi.fn(),
  useUpsertOidcConfig: () => ({ mutate: mutateMock, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useOidcConfig } from "@/hooks/useOidcConfig";

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={qc}><OidcConfigPage /></QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("OidcConfigPage", () => {
  it("form vide si pas de config", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const inputs = screen.getAllByRole("textbox");
    inputs.forEach((input) => expect((input as HTMLInputElement).value).toBe(""));
  });

  it("form pré-rempli si config existante", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: {
        issuer: "https://kc.example.com/realms/test",
        client_id: "rag",
        client_secret_ref: "kc_rag_secret",
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    expect(screen.getByDisplayValue("https://kc.example.com/realms/test")).toBeInTheDocument();
    expect(screen.getByDisplayValue("rag")).toBeInTheDocument();
    expect(screen.getByDisplayValue("kc_rag_secret")).toBeInTheDocument();
  });

  it("Save désactivé tant que non-dirty", () => {
    vi.mocked(useOidcConfig).mockReturnValue({
      data: {
        issuer: "https://kc.example.com/realms/test",
        client_id: "rag",
        client_secret_ref: "kc_rag_secret",
      },
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const save = screen.getByText(/^Enregistrer$/i).closest("button");
    expect(save).toBeDisabled();
  });

  it("submit avec valeurs valides appelle upsert.mutate", async () => {
    mutateMock.mockClear();
    vi.mocked(useOidcConfig).mockReturnValue({
      data: null,
      isLoading: false,
    } as unknown as ReturnType<typeof useOidcConfig>);
    renderPage();
    const inputs = screen.getAllByRole("textbox");
    fireEvent.change(inputs[0], { target: { value: "https://kc.example.com/realms/test" } });
    fireEvent.change(inputs[1], { target: { value: "rag" } });
    fireEvent.change(inputs[2], { target: { value: "kc_rag_secret" } });
    fireEvent.click(screen.getByText(/^Enregistrer$/i));
    await waitFor(() => expect(mutateMock).toHaveBeenCalled());
    expect(mutateMock.mock.calls[0][0]).toEqual({
      issuer: "https://kc.example.com/realms/test",
      client_id: "rag",
      client_secret_ref: "kc_rag_secret",
    });
  });
});
```

- [ ] **Step 6: Run tests**

```bash
cd frontend
npm test -- --run
```

Expected : nouveaux tests PASS + 0 régression sur les tests M6/M7a existants.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/fr/oidc.json \
        frontend/src/i18n/en/oidc.json \
        frontend/src/lib/i18n.ts \
        frontend/src/pages/__tests__/OidcConfigPage.test.tsx
git commit -m "feat(M7b-T5): i18n FR+EN + tests Vitest + audit strings"
```

---

## Auto-revue post-rédaction

**1. Spec coverage :**
- Spec §3 fix backend → Task 1.
- Spec §4 fichiers frontend → Tasks 2-5.
- Spec §5 layout + comportement upsert/Cancel/Save → Task 4.
- Spec §6 sidebar+route → Task 3.
- Spec §7 i18n → Task 5.
- Spec §8 tests → Task 5.

**2. Placeholder scan :** Aucun "TBD", "TODO" ; chaque step a son code ou commande complète.

**3. Type consistency :** `OidcConfig`, `OidcConfigCreate` cohérents Tasks 2, 4, 5. Hooks signatures matchent : `useOidcConfig()` retourne `OidcConfig | null` (via 503 → null), `useUpsertOidcConfig().mutate(OidcConfigCreate)`.

**Note :** la spec design mentionnait 404 pour "non configuré" mais le backend renvoie 503 — c'est aligné dans le plan (Task 2 step 3 intercepte 503).
