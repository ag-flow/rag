# M8b — Frontend Rerank Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer un onglet "Rerank" dans `WorkspaceDetailPanel` permettant aux admins de visualiser/créer/modifier/supprimer la config rerank par workspace, en consommant les endpoints M8 (`GET/PUT/DELETE /api/admin/workspaces/{name}/rerank`).

**Architecture:** Suit le pattern singleton-form de `OidcConfigPage` (M7b) : `useQuery` filtré sur 404 `rerank_not_configured` → `null` ; form `react-hook-form` + Zod `superRefine` pour validation conditionnelle par provider ; `useMutation` PUT/DELETE avec invalidation du cache `["workspace", name, "rerank"]`. Onglet branché dans `WorkspaceDetailPanel` à côté de `Modèle`.

**Tech Stack:** TypeScript strict, React 18, react-hook-form, Zod, TanStack Query, shadcn/ui (`Select`, `AlertDialog`, `Input`, `Button`), react-i18next, Vitest + React Testing Library.

---

## Pré-requis

- Branche actuelle : `dev` (vérifier `git branch --show-current` avant de coder).
- Backend M8 livré (endpoints `GET/PUT/DELETE /api/admin/workspaces/{name}/rerank` disponibles).
- Tous les tests existants passent : `cd frontend && npm test && npx tsc --noEmit && npm run lint`.

## File Structure

**Créés** :
- `frontend/src/lib/rerank.types.ts` — types TS miroirs Pydantic.
- `frontend/src/lib/rerank.ts` — API client (`rerankApi.{get,upsert,delete}`).
- `frontend/src/hooks/useRerank.ts` — hooks React Query.
- `frontend/src/pages/workspace/WorkspaceRerankTab.tsx` — composant onglet (form + état vide/configuré).
- `frontend/src/pages/workspace/DeleteRerankAlert.tsx` — AlertDialog DELETE.
- `frontend/src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx` — tests Vitest du composant.
- `frontend/src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx` — tests Vitest de l'AlertDialog.
- `frontend/src/lib/__tests__/api.test.ts` — test unitaire de `isErrorBodyWithDetail` (nouveau fichier, premier test sur `lib/api.ts`).

**Modifiés** :
- `frontend/src/lib/api.ts` — ajout méthode `put` et helper `isErrorBodyWithDetail`.
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` — ajout `<TabsTrigger>` et `<TabsContent>` rerank.
- `frontend/src/i18n/fr/workspace.json` — ajout section `rerank.*` + `tabs.rerank`.
- `frontend/src/i18n/en/workspace.json` — idem en anglais.

---

## Task 1 — Plomberie API : `api.put` + `isErrorBodyWithDetail`

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Create: `frontend/src/lib/__tests__/api.test.ts`

- [ ] **Step 1.1 : Écrire le test rouge `isErrorBodyWithDetail`**

Créer `frontend/src/lib/__tests__/api.test.ts` :

```typescript
import { describe, it, expect } from "vitest";
import { isErrorBodyWithDetail } from "@/lib/api";

describe("isErrorBodyWithDetail", () => {
  it("retourne true si body.detail === expected", () => {
    expect(isErrorBodyWithDetail({ detail: "rerank_not_configured" }, "rerank_not_configured")).toBe(true);
  });

  it("retourne false si body.detail !== expected", () => {
    expect(isErrorBodyWithDetail({ detail: "workspace_not_found" }, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body n'a pas de champ detail", () => {
    expect(isErrorBodyWithDetail({ message: "boom" }, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est null", () => {
    expect(isErrorBodyWithDetail(null, "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body est une string", () => {
    expect(isErrorBodyWithDetail("oops", "rerank_not_configured")).toBe(false);
  });

  it("retourne false si body.detail n'est pas une string", () => {
    expect(isErrorBodyWithDetail({ detail: 42 }, "rerank_not_configured")).toBe(false);
  });
});
```

- [ ] **Step 1.2 : Lancer le test pour vérifier qu'il échoue**

```bash
cd frontend && npm test -- src/lib/__tests__/api.test.ts
```

Attendu : échec avec `isErrorBodyWithDetail is not exported from "@/lib/api"`.

- [ ] **Step 1.3 : Implémenter `isErrorBodyWithDetail` et `api.put`**

Modifier `frontend/src/lib/api.ts` :

```typescript
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

export function isErrorBodyWithDetail(body: unknown, expected: string): boolean {
  return (
    typeof body === "object" &&
    body !== null &&
    "detail" in body &&
    typeof (body as { detail: unknown }).detail === "string" &&
    (body as { detail: string }).detail === expected
  );
}

async function request<T>(
  url: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(url, {
    ...init,
    credentials: "include",
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

  put: <T>(url: string, body: unknown): Promise<T> =>
    request<T>(url, {
      method: "PUT",
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

- [ ] **Step 1.4 : Lancer le test pour vérifier qu'il passe**

```bash
cd frontend && npm test -- src/lib/__tests__/api.test.ts
```

Attendu : 6 tests PASS.

- [ ] **Step 1.5 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 1.6 : Commit**

```bash
git add frontend/src/lib/api.ts frontend/src/lib/__tests__/api.test.ts
git commit -m "feat(M8b-T1): api.put + helper isErrorBodyWithDetail + tests"
```

---

## Task 2 — Types TS + API client rerank

**Files:**
- Create: `frontend/src/lib/rerank.types.ts`
- Create: `frontend/src/lib/rerank.ts`

- [ ] **Step 2.1 : Créer les types TS**

Créer `frontend/src/lib/rerank.types.ts` :

```typescript
// Miroir des schemas Pydantic backend (cf. backend/src/rag/schemas/admin.py).
// `RerankConfig` correspond à RerankConfigResponse.
// `RerankSpec` correspond à RerankSpec (body PUT).

export type RerankProvider = "cohere" | "voyage" | "ollama";

export type RerankConfig = {
  workspace_id: string;
  provider: RerankProvider;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
  created_at: string;
  updated_at: string;
};

export type RerankSpec = {
  provider: RerankProvider;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
  top_k_pre_rerank: number;
};
```

- [ ] **Step 2.2 : Créer le client API**

Créer `frontend/src/lib/rerank.ts` :

```typescript
import { api } from "@/lib/api";
import type { RerankConfig, RerankSpec } from "@/lib/rerank.types";

const base = (name: string) => `/api/admin/workspaces/${name}/rerank`;

export const rerankApi = {
  get: (name: string) => api.get<RerankConfig>(base(name)),
  upsert: (name: string, payload: RerankSpec) =>
    api.put<RerankConfig>(base(name), payload),
  delete: (name: string) => api.delete<void>(base(name)),
};
```

- [ ] **Step 2.3 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 2.4 : Commit**

```bash
git add frontend/src/lib/rerank.types.ts frontend/src/lib/rerank.ts
git commit -m "feat(M8b-T2): types TS + API client rerank"
```

---

## Task 3 — Hooks React Query

**Files:**
- Create: `frontend/src/hooks/useRerank.ts`

- [ ] **Step 3.1 : Créer les hooks**

Créer `frontend/src/hooks/useRerank.ts` :

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, isErrorBodyWithDetail } from "@/lib/api";
import { rerankApi } from "@/lib/rerank";
import type { RerankConfig, RerankSpec } from "@/lib/rerank.types";

/**
 * Récupère la config rerank du workspace.
 * Backend renvoie 404 detail="rerank_not_configured" quand pas configuré
 * (cf. backend/src/rag/api/admin/workspaces_rerank.py) — on intercepte ce
 * cas et retourne null pour permettre au composant d'afficher un form vide.
 * Les autres 404 (workspace_not_found) et erreurs sont propagées.
 */
export function useRerankConfig(name: string, enabled: boolean) {
  return useQuery<RerankConfig | null>({
    queryKey: ["workspace", name, "rerank"],
    queryFn: async () => {
      try {
        return await rerankApi.get(name);
      } catch (err) {
        if (
          err instanceof ApiError &&
          err.status === 404 &&
          isErrorBodyWithDetail(err.body, "rerank_not_configured")
        ) {
          return null;
        }
        throw err;
      }
    },
    enabled,
  });
}

export function useUpsertRerankConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<RerankConfig, Error, RerankSpec>({
    mutationFn: (payload) => rerankApi.upsert(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "rerank"] });
    },
  });
}

export function useDeleteRerankConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => rerankApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "rerank"] });
    },
  });
}
```

- [ ] **Step 3.2 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 3.3 : Commit**

```bash
git add frontend/src/hooks/useRerank.ts
git commit -m "feat(M8b-T3): hooks useRerank (Query + Upsert + Delete)"
```

---

## Task 4 — i18n FR + EN

**Files:**
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Step 4.1 : Ajouter `tabs.rerank` + section `rerank` (FR)**

Modifier `frontend/src/i18n/fr/workspace.json` :

1. Dans la clé `tabs`, ajouter `"rerank": "Rerank"` après `"model": "Modèle"`.
2. Ajouter la section `rerank` à la racine, après la section `model` et avant `dialog` :

```json
  "rerank": {
    "title": "Reranking",
    "titleOptional": "Reranking (optionnel)",
    "badge": {
      "active": "actif"
    },
    "description": {
      "configured": "Activé pour ce workspace. Les hits pgvector sont retriés par le modèle sélectionné avant retour MCP.",
      "empty": "Ajoute une seconde passe de tri sur les hits pgvector. Si désactivé, le tri par similarité cosinus seul est utilisé."
    },
    "fields": {
      "provider": "Provider",
      "providerPlaceholder": "Sélectionner…",
      "providers": {
        "cohere": "Cohere",
        "voyage": "Voyage AI",
        "ollama": "Ollama"
      },
      "model": "Modèle",
      "modelPlaceholder": "ex. rerank-english-v3.0",
      "baseUrl": "Base URL (Ollama)",
      "baseUrlPlaceholder": "https://ollama.example.com",
      "baseUrlNotApplicable": "— non applicable —",
      "apiKeyRef": "Référence clé API Harpocrate",
      "apiKeyRefPlaceholder": "cohere_rerank_key",
      "apiKeyRefNotApplicable": "— non applicable —",
      "topK": "top_k pré-rerank",
      "topKHelp": "(1-500)"
    },
    "errors": {
      "required": "Champ requis.",
      "required_for_provider": "Requis pour ce provider.",
      "alphanum_underscore_only": "Caractères autorisés : a-z, A-Z, 0-9, underscore.",
      "invalid_url": "URL invalide.",
      "min": "Doit être ≥ 1.",
      "max": "Doit être ≤ 500."
    },
    "warning": "Si le provider tombe, la recherche échoue (pas de fallback silencieux). Cohérent avec la philosophie fail-fast.",
    "lastModified": "Dernière modification : {{when}}",
    "actions": {
      "save": "Enregistrer",
      "activate": "Activer",
      "cancel": "Annuler",
      "delete": "Supprimer la config"
    },
    "save": {
      "success": "Configuration enregistrée.",
      "error": "Échec de l'enregistrement."
    },
    "delete": {
      "title": "Désactiver le reranking ?",
      "warning": "La configuration rerank de ce workspace sera supprimée. Les prochaines recherches utiliseront uniquement la similarité cosinus pgvector.",
      "reversibleNote": "Cette action est réversible (recréer la config).",
      "confirm": "Désactiver",
      "success": "Configuration supprimée.",
      "error": "Échec de la suppression."
    }
  },
```

- [ ] **Step 4.2 : Ajouter `tabs.rerank` + section `rerank` (EN)**

Modifier `frontend/src/i18n/en/workspace.json` (mêmes positions) :

1. `tabs.rerank`: `"Rerank"`.
2. Section `rerank` :

```json
  "rerank": {
    "title": "Reranking",
    "titleOptional": "Reranking (optional)",
    "badge": {
      "active": "active"
    },
    "description": {
      "configured": "Enabled for this workspace. pgvector hits are re-ranked by the selected model before MCP return.",
      "empty": "Adds a second pass to rank pgvector hits. If disabled, only cosine similarity is used."
    },
    "fields": {
      "provider": "Provider",
      "providerPlaceholder": "Select…",
      "providers": {
        "cohere": "Cohere",
        "voyage": "Voyage AI",
        "ollama": "Ollama"
      },
      "model": "Model",
      "modelPlaceholder": "e.g. rerank-english-v3.0",
      "baseUrl": "Base URL (Ollama)",
      "baseUrlPlaceholder": "https://ollama.example.com",
      "baseUrlNotApplicable": "— not applicable —",
      "apiKeyRef": "Harpocrate API key reference",
      "apiKeyRefPlaceholder": "cohere_rerank_key",
      "apiKeyRefNotApplicable": "— not applicable —",
      "topK": "top_k pre-rerank",
      "topKHelp": "(1-500)"
    },
    "errors": {
      "required": "Required field.",
      "required_for_provider": "Required for this provider.",
      "alphanum_underscore_only": "Allowed characters: a-z, A-Z, 0-9, underscore.",
      "invalid_url": "Invalid URL.",
      "min": "Must be ≥ 1.",
      "max": "Must be ≤ 500."
    },
    "warning": "If the provider fails, search fails (no silent fallback). Consistent with fail-fast philosophy.",
    "lastModified": "Last modified: {{when}}",
    "actions": {
      "save": "Save",
      "activate": "Activate",
      "cancel": "Cancel",
      "delete": "Delete config"
    },
    "save": {
      "success": "Configuration saved.",
      "error": "Failed to save configuration."
    },
    "delete": {
      "title": "Disable reranking?",
      "warning": "The rerank configuration of this workspace will be removed. Future searches will only use pgvector cosine similarity.",
      "reversibleNote": "This action is reversible (recreate the config).",
      "confirm": "Disable",
      "success": "Configuration removed.",
      "error": "Failed to remove configuration."
    }
  },
```

- [ ] **Step 4.3 : Vérifier que les JSON parsent**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur (Vite/TS parse les JSON imports).

- [ ] **Step 4.4 : Commit**

```bash
git add frontend/src/i18n/fr/workspace.json frontend/src/i18n/en/workspace.json
git commit -m "feat(M8b-T4): i18n FR + EN section rerank + tabs.rerank"
```

---

## Task 5 — Composant `WorkspaceRerankTab` (TDD)

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceRerankTab.tsx`
- Create: `frontend/src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx`

- [ ] **Step 5.1 : Écrire le squelette de test (rouge)**

Créer `frontend/src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx` :

```typescript
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceRerankTab } from "@/pages/workspace/WorkspaceRerankTab";
import type { Workspace } from "@/lib/workspaces.types";
import type { RerankConfig } from "@/lib/rerank.types";

const upsertMutate = vi.fn();

vi.mock("@/hooks/useRerank", () => ({
  useRerankConfig: vi.fn(),
  useUpsertRerankConfig: () => ({ mutate: upsertMutate, isPending: false }),
  useDeleteRerankConfig: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useRerankConfig } from "@/hooks/useRerank";

const mockWorkspace: Workspace = {
  id: "ws-1",
  name: "my-workspace",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: "openai_key",
    base_url: null,
  },
  sources_count: 0,
  documents_count: 0,
  last_indexed_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const mockConfig: RerankConfig = {
  workspace_id: "ws-1",
  provider: "cohere",
  model: "rerank-english-v3.0",
  api_key_ref: "cohere_rerank_key",
  base_url: null,
  top_k_pre_rerank: 50,
  created_at: "2026-05-18T10:00:00Z",
  updated_at: "2026-05-18T10:00:00Z",
};

function mockState(data: RerankConfig | null, isLoading = false) {
  vi.mocked(useRerankConfig).mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useRerankConfig>);
}

describe("WorkspaceRerankTab", () => {
  it("état vide : form vide + bouton Activer + pas de bouton Supprimer", () => {
    mockState(null);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/Reranking \(optionnel\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/^actif$/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Activer/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Supprimer la config/i })).not.toBeInTheDocument();
  });

  it("état configuré : form pré-rempli + badge actif + bouton Supprimer", () => {
    mockState(mockConfig);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/^actif$/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("rerank-english-v3.0")).toBeInTheDocument();
    expect(screen.getByDisplayValue("cohere_rerank_key")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enregistrer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Supprimer la config/i })).toBeInTheDocument();
  });

  it("submit avec valeurs valides appelle upsert.mutate avec le payload", async () => {
    upsertMutate.mockClear();
    mockState(mockConfig);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    const modelInput = screen.getByDisplayValue("rerank-english-v3.0");
    fireEvent.change(modelInput, { target: { value: "rerank-multilingual-v3.0" } });
    fireEvent.click(screen.getByRole("button", { name: /Enregistrer/i }));
    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    expect(upsertMutate.mock.calls[0][0]).toMatchObject({
      provider: "cohere",
      model: "rerank-multilingual-v3.0",
      api_key_ref: "cohere_rerank_key",
      top_k_pre_rerank: 50,
    });
  });

  it("affiche la dernière modification quand configuré", () => {
    mockState({ ...mockConfig, updated_at: new Date(Date.now() - 2 * 3600_000).toISOString() });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/Dernière modification/i)).toBeInTheDocument();
  });

  it("ne rend pas le footer lastModified quand non configuré", () => {
    mockState(null);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.queryByText(/Dernière modification/i)).not.toBeInTheDocument();
  });
});
```

- [ ] **Step 5.2 : Lancer le test pour vérifier qu'il échoue**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx
```

Attendu : échec — `WorkspaceRerankTab` n'existe pas.

- [ ] **Step 5.3 : Implémenter `WorkspaceRerankTab`**

Créer `frontend/src/pages/workspace/WorkspaceRerankTab.tsx` :

```typescript
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useToast } from "@/hooks/useToast";
import {
  useRerankConfig,
  useUpsertRerankConfig,
} from "@/hooks/useRerank";
import { DeleteRerankAlert } from "./DeleteRerankAlert";
import type { Workspace } from "@/lib/workspaces.types";
import type { RerankProvider } from "@/lib/rerank.types";

const PROVIDERS: RerankProvider[] = ["cohere", "voyage", "ollama"];

const schema = z
  .object({
    provider: z.enum(["cohere", "voyage", "ollama"]),
    model: z.string().min(1, "required"),
    api_key_ref: z
      .string()
      .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only")
      .nullable(),
    base_url: z.string().url("invalid_url").nullable(),
    top_k_pre_rerank: z.coerce
      .number()
      .int()
      .min(1, "min")
      .max(500, "max"),
  })
  .superRefine((data, ctx) => {
    if ((data.provider === "cohere" || data.provider === "voyage") && !data.api_key_ref) {
      ctx.addIssue({
        path: ["api_key_ref"],
        code: z.ZodIssueCode.custom,
        message: "required_for_provider",
      });
    }
    if (data.provider === "ollama" && !data.base_url) {
      ctx.addIssue({
        path: ["base_url"],
        code: z.ZodIssueCode.custom,
        message: "required_for_provider",
      });
    }
  });

type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = {
  provider: "cohere",
  model: "",
  api_key_ref: null,
  base_url: null,
  top_k_pre_rerank: 50,
};

function relativeTime(iso: string, t: (k: string, opts?: object) => string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return t("time.justNow");
  if (m < 60) return t("time.minutesAgo", { count: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t("time.hoursAgo", { count: h });
  return t("time.daysAgo", { count: Math.floor(h / 24) });
}

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceRerankTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data, isLoading } = useRerankConfig(workspace.name, enabled);
  const upsert = useUpsertRerankConfig(workspace.name);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });

  useEffect(() => {
    if (isLoading) return;
    if (data) {
      form.reset({
        provider: data.provider,
        model: data.model,
        api_key_ref: data.api_key_ref,
        base_url: data.base_url,
        top_k_pre_rerank: data.top_k_pre_rerank,
      });
    } else {
      form.reset(EMPTY);
    }
  }, [data, isLoading, form]);

  const provider = form.watch("provider");
  const apiKeyApplicable = provider === "cohere" || provider === "voyage";
  const baseUrlApplicable = provider === "ollama";

  const onSubmit = (values: FormValues) => {
    const payload = {
      provider: values.provider,
      model: values.model,
      api_key_ref: apiKeyApplicable ? values.api_key_ref : null,
      base_url: baseUrlApplicable ? values.base_url : null,
      top_k_pre_rerank: values.top_k_pre_rerank,
    };
    upsert.mutate(payload, {
      onSuccess: (saved) => {
        toast({ title: t("rerank.save.success") });
        form.reset({
          provider: saved.provider,
          model: saved.model,
          api_key_ref: saved.api_key_ref,
          base_url: saved.base_url,
          top_k_pre_rerank: saved.top_k_pre_rerank,
        });
      },
      onError: () =>
        toast({ title: t("rerank.save.error"), variant: "destructive" }),
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  const configured = data !== null && data !== undefined;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          {configured ? t("rerank.title") : t("rerank.titleOptional")}
          {configured && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {t("rerank.badge.active")}
            </span>
          )}
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          {configured ? t("rerank.description.configured") : t("rerank.description.empty")}
        </p>
      </div>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4 rounded-md border bg-white p-4"
      >
        {/* Provider */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.provider")}
          </label>
          <Controller
            name="provider"
            control={form.control}
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(v) => field.onChange(v as RerankProvider)}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("rerank.fields.providerPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {t(`rerank.fields.providers.${p}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        {/* Modèle */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.model")}
          </label>
          <Input
            {...form.register("model")}
            placeholder={t("rerank.fields.modelPlaceholder")}
            className="mt-1 font-mono"
          />
          {form.formState.errors.model && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.model.message ?? "required"}`)}
            </p>
          )}
        </div>

        {/* Base URL */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.baseUrl")}
          </label>
          <Input
            {...form.register("base_url", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
            disabled={!baseUrlApplicable}
            placeholder={
              baseUrlApplicable
                ? t("rerank.fields.baseUrlPlaceholder")
                : t("rerank.fields.baseUrlNotApplicable")
            }
            className="mt-1 font-mono"
          />
          {form.formState.errors.base_url && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.base_url.message ?? "invalid_url"}`)}
            </p>
          )}
        </div>

        {/* API key ref */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.apiKeyRef")}
          </label>
          <Input
            {...form.register("api_key_ref", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
            disabled={!apiKeyApplicable}
            placeholder={
              apiKeyApplicable
                ? t("rerank.fields.apiKeyRefPlaceholder")
                : t("rerank.fields.apiKeyRefNotApplicable")
            }
            className="mt-1 font-mono"
          />
          {form.formState.errors.api_key_ref && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.api_key_ref.message ?? "required"}`)}
            </p>
          )}
        </div>

        {/* top_k pre-rerank */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.topK")}{" "}
            <span className="text-slate-500 font-normal">
              {t("rerank.fields.topKHelp")}
            </span>
          </label>
          <Input
            type="number"
            min={1}
            max={500}
            {...form.register("top_k_pre_rerank", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          {form.formState.errors.top_k_pre_rerank && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.top_k_pre_rerank.message ?? "required"}`)}
            </p>
          )}
        </div>

        {configured && data && (
          <p className="text-xs text-slate-500">
            {t("rerank.lastModified", { when: relativeTime(data.updated_at, t) })}
          </p>
        )}

        <div className="flex items-center justify-between pt-2">
          <div>
            {configured && (
              <Button
                type="button"
                variant="outline"
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={() => setDeleteOpen(true)}
              >
                {t("rerank.actions.delete")}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => form.reset(data ?? EMPTY)}
              disabled={!form.formState.isDirty}
            >
              {t("rerank.actions.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={!form.formState.isDirty || upsert.isPending}
            >
              {configured ? t("rerank.actions.save") : t("rerank.actions.activate")}
            </Button>
          </div>
        </div>
      </form>

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("rerank.warning")}</p>
      </div>

      <DeleteRerankAlert
        name={workspace.name}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </div>
  );
}
```

- [ ] **Step 5.4 : Lancer le test (encore rouge à cause de DeleteRerankAlert non créé)**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx
```

Attendu : échec import `DeleteRerankAlert`. C'est normal — il sera créé en Task 6. Continuer.

- [ ] **Step 5.5 : Stub temporaire `DeleteRerankAlert` pour faire passer le test**

Créer `frontend/src/pages/workspace/DeleteRerankAlert.tsx` (stub minimal qui sera étoffé en Task 6) :

```typescript
interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function DeleteRerankAlert(_props: Props) {
  return null;
}
```

> Note : ce stub permet de tester `WorkspaceRerankTab` en isolation. Task 6 implémente le composant complet et ses tests.

- [ ] **Step 5.6 : Lancer le test pour vérifier qu'il passe**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx
```

Attendu : 5 tests PASS.

- [ ] **Step 5.7 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 5.8 : Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceRerankTab.tsx \
        frontend/src/pages/workspace/DeleteRerankAlert.tsx \
        frontend/src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx
git commit -m "feat(M8b-T5): WorkspaceRerankTab (form + Zod conditionnel) + tests"
```

---

## Task 6 — Composant `DeleteRerankAlert` (TDD)

**Files:**
- Modify: `frontend/src/pages/workspace/DeleteRerankAlert.tsx`
- Create: `frontend/src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx`

- [ ] **Step 6.1 : Écrire le test rouge**

Créer `frontend/src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx` :

```typescript
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { DeleteRerankAlert } from "@/pages/workspace/DeleteRerankAlert";

const deleteMutate = vi.fn();
const toastMock = vi.fn();

vi.mock("@/hooks/useRerank", () => ({
  useDeleteRerankConfig: () => ({ mutate: deleteMutate, isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

describe("DeleteRerankAlert", () => {
  it("ne rend rien quand open=false", () => {
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={false} onOpenChange={() => {}} />,
    );
    expect(screen.queryByText(/Désactiver le reranking/i)).not.toBeInTheDocument();
  });

  it("rend le dialog quand open=true", () => {
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={true} onOpenChange={() => {}} />,
    );
    expect(screen.getByText(/Désactiver le reranking/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Annuler/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Désactiver$/i })).toBeInTheDocument();
  });

  it("appelle useDeleteRerankConfig.mutate au clic sur Désactiver", async () => {
    deleteMutate.mockClear();
    const onOpenChange = vi.fn();
    renderWithProviders(
      <DeleteRerankAlert name="ws-1" open={true} onOpenChange={onOpenChange} />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Désactiver$/i }));
    await waitFor(() => expect(deleteMutate).toHaveBeenCalledOnce());
  });
});
```

- [ ] **Step 6.2 : Lancer le test pour vérifier qu'il échoue**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx
```

Attendu : 2 échecs sur 3 (le stub Task 5 retourne `null` donc « ne rend rien » passe, les deux autres échouent).

- [ ] **Step 6.3 : Implémenter le composant complet**

Remplacer le contenu de `frontend/src/pages/workspace/DeleteRerankAlert.tsx` :

```typescript
import { useTranslation } from "react-i18next";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteRerankConfig } from "@/hooks/useRerank";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function DeleteRerankAlert({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const del = useDeleteRerankConfig(name);

  const handleConfirm = () => {
    del.mutate(undefined, {
      onSuccess: () => {
        toast({ title: t("rerank.delete.success") });
        onOpenChange(false);
      },
      onError: () =>
        toast({ title: t("rerank.delete.error"), variant: "destructive" }),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("rerank.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("rerank.delete.warning")}
            <br />
            <span className="mt-2 inline-block text-slate-500">
              {t("rerank.delete.reversibleNote")}
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            className="bg-red-600 hover:bg-red-700"
          >
            {t("rerank.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 6.4 : Lancer les tests pour vérifier qu'ils passent**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx
```

Attendu : 3 tests PASS.

- [ ] **Step 6.5 : Relancer aussi `WorkspaceRerankTab.test.tsx` pour s'assurer qu'il passe toujours**

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx
```

Attendu : 5 tests PASS.

- [ ] **Step 6.6 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 6.7 : Commit**

```bash
git add frontend/src/pages/workspace/DeleteRerankAlert.tsx \
        frontend/src/pages/workspace/__tests__/DeleteRerankAlert.test.tsx
git commit -m "feat(M8b-T6): DeleteRerankAlert (AlertDialog) + tests"
```

---

## Task 7 — Branchement onglet dans `WorkspaceDetailPanel`

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Step 7.1 : Ajouter le `TabsTrigger` et `TabsContent` rerank**

Modifier `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` :

1. Ajouter l'import en haut, après `import { WorkspaceModelTab } from "./WorkspaceModelTab";` :

```typescript
import { WorkspaceRerankTab } from "./WorkspaceRerankTab";
```

2. Dans `<TabsList>`, ajouter après `<TabsTrigger value="model">{t("tabs.model")}</TabsTrigger>` :

```tsx
          <TabsTrigger value="rerank">{t("tabs.rerank")}</TabsTrigger>
```

3. Après le `<TabsContent value="model">` block, ajouter :

```tsx
        <TabsContent value="rerank" className="pt-4">
          <WorkspaceRerankTab workspace={ws} enabled={activeTab === "rerank"} />
        </TabsContent>
```

Le fichier final doit avoir :

```tsx
        <TabsList>
          <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
          <TabsTrigger value="sources">
            {t("tabs.sources", { count: ws.sources_count })}
          </TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
          <TabsTrigger value="model">{t("tabs.model")}</TabsTrigger>
          <TabsTrigger value="rerank">{t("tabs.rerank")}</TabsTrigger>
        </TabsList>
```

Et plus bas :

```tsx
        <TabsContent value="model" className="pt-4">
          <WorkspaceModelTab workspace={ws} />
        </TabsContent>
        <TabsContent value="rerank" className="pt-4">
          <WorkspaceRerankTab workspace={ws} enabled={activeTab === "rerank"} />
        </TabsContent>
```

- [ ] **Step 7.2 : Vérifier `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 7.3 : Lancer tous les tests Vitest**

```bash
cd frontend && npm test
```

Attendu : 100 % PASS (aucun test cassé par l'ajout de l'onglet).

- [ ] **Step 7.4 : Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceDetailPanel.tsx
git commit -m "feat(M8b-T7): onglet Rerank branché dans WorkspaceDetailPanel"
```

---

## Task 8 — Validation finale : lint + tsc + smoke manuel + doc roadmap

**Files:**
- Modify: `specs/09-roadmap.md`

- [ ] **Step 8.1 : Lint frontend**

```bash
cd frontend && npm run lint
```

Attendu : aucune erreur. Corriger inline si besoin.

- [ ] **Step 8.2 : Vérification `tsc --noEmit`**

```bash
cd frontend && npx tsc --noEmit
```

Attendu : aucune erreur.

- [ ] **Step 8.3 : Vérification suite Vitest complète**

```bash
cd frontend && npm test
```

Attendu : tous les tests PASS.

- [ ] **Step 8.4 : Audit strings (pattern M7b-T5)**

Vérifier qu'aucune chaîne brute n'apparaît dans les composants nouveaux. Grep :

```bash
cd frontend && grep -n '>[A-Z][a-zA-Zàâäéèêëîïôöùûüç ]\{2,\}<' \
  src/pages/workspace/WorkspaceRerankTab.tsx \
  src/pages/workspace/DeleteRerankAlert.tsx
```

Attendu : aucune ligne sortie (tout est i18n via `t(...)`).

- [ ] **Step 8.5 : Smoke manuel (dev server)**

```bash
cd frontend && npm run dev
```

Dans un autre terminal, démarrer le backend test :
```bash
./scripts/run-test.sh
```

Naviguer dans le navigateur sur `http://localhost:5173`, se connecter, ouvrir un workspace existant. Vérifier les 6 points suivants :

1. L'onglet « Rerank » apparaît en 5e position.
2. Sur un workspace sans config : titre « Reranking (optionnel) », form vide, bouton « Activer », pas de badge actif, pas de bouton « Supprimer la config ».
3. Switch provider → ollama : `base_url` activé, `api_key_ref` disabled avec helper text. Switch provider → cohere : inverse.
4. Remplir le form en cohere (modèle = `rerank-english-v3.0`, api_key_ref = `cohere_rerank_key`), cliquer « Activer ». Toast succès. Titre passe à « Reranking » + badge `● actif`, bouton « Supprimer la config » apparaît, footer « Dernière modification : à l'instant ».
5. Cliquer « Supprimer la config » → dialog → confirmer → toast succès → retour à l'état vide.
6. Aucune erreur dans la console navigateur.

- [ ] **Step 8.6 : Mettre à jour `specs/09-roadmap.md`**

Dans `specs/09-roadmap.md` § Reranking, remplacer la dernière ligne :

```
Frontend (onglet "Rerank" dans WorkspaceDetailPanel) → jalon M8b à venir.
```

par :

```
Frontend livré en M8b (onglet "Rerank" dans `WorkspaceDetailPanel`) — cf. `docs/superpowers/specs/2026-05-18-M8b-frontend-rerank-design.md`.
```

- [ ] **Step 8.7 : Commit final**

```bash
git add specs/09-roadmap.md
git commit -m "docs(M8b-T8): roadmap marque M8b livré (frontend rerank)"
```

---

## Self-Review (notes pour le rédacteur, à supprimer mentalement après lecture)

**Spec coverage** : chaque section de la spec a au moins une tâche :
- §3 Maquettes → Task 5 (états vide/configuré) + Task 6 (AlertDialog).
- §4 Modèle de données → Tasks 1 (api.put + helper), 2 (types + api client).
- §5 Validation Zod → Task 5 step 5.3 (schema complet avec superRefine).
- §6 Composants → Tasks 5, 6, 7.
- §7 i18n → Task 4.
- §8 Tests Vitest → Tasks 1, 5, 6 (couverture 9 cas listés répartis sur les composants).
- §9 Plan d'attaque → Tasks 1-8 (recompactés de 7 vers 8 pour découper plomberie/types/hooks/i18n proprement).
- §10 Hors-scope → respecté (pas de "tester la config", pas de badge sur le TabsTrigger, pas de StatusIndicator).

**Placeholder scan** : aucun TBD/TODO/à compléter dans le plan, toutes les commandes et tous les blocs de code sont complets.

**Type consistency** : `RerankProvider`, `RerankConfig`, `RerankSpec` définis en Task 2 et utilisés tels quels dans Tasks 3, 5, 6. Hooks `useRerankConfig(name, enabled)`, `useUpsertRerankConfig(name)`, `useDeleteRerankConfig(name)` consistants entre Task 3 (définition) et Tasks 5, 6 (consommation).
