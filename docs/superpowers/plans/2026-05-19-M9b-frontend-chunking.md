# M9b — Frontend Chunking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer l'onglet `Chunking` dans `WorkspaceDetailPanel` : form Zod + hooks React Query + AlertDialog de confirmation reindex + tests symétriques M8b. Aucun changement backend (M9 livré). Config obligatoire (pas de DELETE), flow 409 optimiste.

**Architecture:** Pattern miroir M8b (rerank). Discrimination 200/202/204/409 via un helper `api.putRaw` retournant la `Response` brute. Un `useUpsertChunkingConfig` qui retourne un union `UpsertChunkingResult`. Le composant gère le state `confirmReindex` pour ouvrir l'AlertDialog quand le backend renvoie 409.

**Tech Stack:** React 18 + TypeScript strict + react-hook-form + zod + TanStack Query + Tailwind + shadcn/ui + i18next + Vitest + React Testing Library. Pattern de référence : `frontend/src/pages/workspace/WorkspaceRerankTab.tsx`, `frontend/src/hooks/useRerank.ts`, `frontend/src/lib/rerank.ts`.

**Spec design** : `docs/superpowers/specs/2026-05-19-M9b-frontend-chunking-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `frontend/src/lib/chunking.types.ts` | **Create** | Types miroir backend : `ChunkingConfig`, `ChunkingSpec`, `ChunkingStrategy`, `ChunkingChangeRequiresReindexBody` |
| `frontend/src/lib/chunking.ts` | **Create** | `chunkingApi.get`, `chunkingApi.upsert(name, payload, confirm)` retournant `UpsertChunkingResult` discriminé ; `isChunkingChangeRequiresReindex` |
| `frontend/src/lib/api.ts` | **Modify** | Ajout `api.putRaw(url, body)` retournant la `Response` brute |
| `frontend/src/lib/workspaces.types.ts` | **Modify** | Étendre `Job.triggered_by` avec `"reindex_indexer_change" | "reindex_chunking_change"` |
| `frontend/src/hooks/useChunking.ts` | **Create** | `useChunkingConfig`, `useUpsertChunkingConfig` |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` | **Create** | Schema Zod + `CHUNKING_STRATEGIES`, `DEFAULT_CHUNKING_FORM` |
| `frontend/src/pages/workspace/ChunkingConfirmReindexAlert.tsx` | **Create** | `AlertDialog` shadcn/ui pour le 409 |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | **Create** | Composant onglet |
| `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` | **Modify** | Ajout 6ᵉ `TabsTrigger` + `TabsContent` |
| `frontend/src/i18n/fr.json` | **Modify** | `tabs.chunking` + section `chunking.*` |
| `frontend/src/i18n/en.json` | **Modify** | Traduction symétrique |
| `frontend/src/lib/__tests__/chunking.test.ts` | **Create** | Tests API client (4 cas status + helper) |
| `frontend/src/hooks/__tests__/useChunking.test.ts` | **Create** | Tests hooks Query + Mutation |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts` | **Create** | Tests Zod (validations) |
| `frontend/src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx` | **Create** | Tests AlertDialog |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx` | **Create** | Tests composant (flows 200/204/409/202) |
| `specs/09-roadmap.md` | **Modify** | Marquer M9b livré (déjà mentionné post-M9, ajuster wording) |

---

## Task 1 — Types + extension `api.putRaw` + extension `Job.triggered_by`

**Files:**
- Create: `frontend/src/lib/chunking.types.ts`
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/lib/workspaces.types.ts`

- [ ] **Step 1: Créer `chunking.types.ts`**

`frontend/src/lib/chunking.types.ts` :

```ts
// Miroir des schemas Pydantic backend (cf. backend/src/rag/schemas/admin.py).
// `ChunkingConfig` correspond à ChunkingConfigResponse.
// `ChunkingSpec` correspond à ChunkingConfigSpec (body PUT).

export type ChunkingStrategy = "paragraph";

export type ChunkingConfig = {
  workspace_id: string;
  strategy: ChunkingStrategy;
  max_chars: number;
  min_chars: number;
  overlap_chars: number;
  extras: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type ChunkingSpec = {
  strategy: ChunkingStrategy;
  max_chars: number;
  min_chars: number;
  overlap_chars: number;
  extras: Record<string, unknown>;
};

export type ChunkingChangeRequiresReindexBody = {
  error: "chunking_change_requires_reindex";
  workspace: string;
  current: string;
  new: string;
  action: string;
};
```

- [ ] **Step 2: Étendre `api.ts` avec `putRaw`**

Modifier `frontend/src/lib/api.ts` — ajouter une nouvelle méthode `putRaw` dans l'objet `api` :

```ts
export const api = {
  // ... helpers existants (get/post/put/patch/delete)

  /**
   * PUT bas-niveau retournant la `Response` brute pour permettre la lecture
   * du status code (200/202/204). Les codes 4xx/5xx remontent comme `Response`
   * également — le caller doit gérer manuellement.
   * Lance `ApiError` UNIQUEMENT pour les codes >= 400.
   */
  putRaw: async (url: string, body: unknown): Promise<Response> => {
    const resp = await fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    });
    if (!resp.ok) {
      let parsed: unknown = null;
      try {
        parsed = await resp.json();
      } catch {
        // pas de body JSON
      }
      throw new ApiError(resp.status, parsed);
    }
    return resp;
  },
};
```

Important : l'ordre alphabétique de l'objet `api` n'est pas strict — l'ajouter après `put` est OK. Vérifier que le code compile (`npx tsc --noEmit`).

- [ ] **Step 3: Étendre `Job.triggered_by`**

Modifier `frontend/src/lib/workspaces.types.ts`, étendre l'union sur `triggered_by` :

```ts
// Remplacer :
// triggered_by: "webhook" | "manual" | "push" | "schedule";
// Par :
triggered_by:
  | "webhook"
  | "manual"
  | "push"
  | "schedule"
  | "reindex_indexer_change"
  | "reindex_chunking_change";
```

(Cela aligne le type frontend avec ce que le backend M5+M9 peut retourner. Aucun caller existant ne sera cassé — c'est un widening.)

- [ ] **Step 4: Compilation TypeScript**

```
cd frontend && npx tsc --noEmit
```

Expected : aucune erreur. Si un caller dépendait du fait que `triggered_by` était limité aux 4 valeurs (ex. `switch` exhaustif sans default), TypeScript va flagger — corriger en ajoutant un cas pour les nouvelles valeurs ou un `default`.

- [ ] **Step 5: Lint + format**

```
cd frontend && npm run lint && npm run format
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/chunking.types.ts frontend/src/lib/api.ts frontend/src/lib/workspaces.types.ts
git commit -m "feat(M9b-T1): types chunking + api.putRaw + extension Job.triggered_by"
```

---

## Task 2 — API client `chunking.ts` + tests

**Files:**
- Create: `frontend/src/lib/chunking.ts`
- Create: `frontend/src/lib/__tests__/chunking.test.ts`

- [ ] **Step 1: Écrire les tests (rouge)**

`frontend/src/lib/__tests__/chunking.test.ts` :

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { chunkingApi, isChunkingChangeRequiresReindex } from "@/lib/chunking";
import { api, ApiError } from "@/lib/api";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

const baseSpec: ChunkingSpec = {
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
};

const baseConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  ...baseSpec,
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

describe("chunkingApi.upsert", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("retourne {status: 'no_change'} sur 204", async () => {
    vi.spyOn(api, "putRaw").mockResolvedValue(new Response(null, { status: 204 }));
    const r = await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(r).toEqual({ status: "no_change" });
  });

  it("retourne {status: 'updated', config} sur 200", async () => {
    vi.spyOn(api, "putRaw").mockResolvedValue(
      new Response(JSON.stringify(baseConfig), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const r = await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(r.status).toBe("updated");
    if (r.status === "updated") {
      expect(r.config.workspace_id).toBe("ws-1");
    }
  });

  it("retourne {status: 'reindex_triggered', job} sur 202", async () => {
    const job = {
      id: "job-1",
      triggered_by: "reindex_chunking_change",
      status: "pending",
      files_changed: 0,
      files_skipped: 0,
      error_message: null,
      started_at: null,
      finished_at: null,
      duration_ms: null,
    };
    vi.spyOn(api, "putRaw").mockResolvedValue(
      new Response(JSON.stringify(job), {
        status: 202,
        headers: { "Content-Type": "application/json" },
      }),
    );
    const r = await chunkingApi.upsert("ws-1", baseSpec, true);
    expect(r.status).toBe("reindex_triggered");
    if (r.status === "reindex_triggered") {
      expect(r.job.triggered_by).toBe("reindex_chunking_change");
    }
  });

  it("propage ApiError sur 409", async () => {
    vi.spyOn(api, "putRaw").mockRejectedValue(
      new ApiError(409, {
        error: "chunking_change_requires_reindex",
        workspace: "ws-1",
        current: "paragraph (max=2000, min=200, overlap=200)",
        new: "paragraph (max=1500, min=100, overlap=150)",
        action: "PUT /workspaces/ws-1/chunking-config?confirm=true",
      }),
    );
    await expect(chunkingApi.upsert("ws-1", baseSpec, false)).rejects.toBeInstanceOf(
      ApiError,
    );
  });

  it("URL inclut ?confirm=true quand confirm=true", async () => {
    const putRawSpy = vi
      .spyOn(api, "putRaw")
      .mockResolvedValue(new Response(null, { status: 204 }));
    await chunkingApi.upsert("ws-1", baseSpec, true);
    expect(putRawSpy).toHaveBeenCalledWith(
      "/api/admin/workspaces/ws-1/chunking-config?confirm=true",
      baseSpec,
    );
  });

  it("URL sans query quand confirm=false", async () => {
    const putRawSpy = vi
      .spyOn(api, "putRaw")
      .mockResolvedValue(new Response(null, { status: 204 }));
    await chunkingApi.upsert("ws-1", baseSpec, false);
    expect(putRawSpy).toHaveBeenCalledWith(
      "/api/admin/workspaces/ws-1/chunking-config",
      baseSpec,
    );
  });
});

describe("isChunkingChangeRequiresReindex", () => {
  it("renvoie true sur le bon shape", () => {
    expect(
      isChunkingChangeRequiresReindex({
        error: "chunking_change_requires_reindex",
        workspace: "ws-1",
        current: "x",
        new: "y",
        action: "z",
      }),
    ).toBe(true);
  });

  it("renvoie false sur autre erreur", () => {
    expect(
      isChunkingChangeRequiresReindex({ error: "workspace_not_found" }),
    ).toBe(false);
  });

  it("renvoie false sur null/non-objet", () => {
    expect(isChunkingChangeRequiresReindex(null)).toBe(false);
    expect(isChunkingChangeRequiresReindex(undefined)).toBe(false);
    expect(isChunkingChangeRequiresReindex("string")).toBe(false);
  });
});
```

- [ ] **Step 2: Lancer (rouge)**

```
cd frontend && npm test -- src/lib/__tests__/chunking.test.ts
```

Expected : tous les tests échouent (`Cannot find module '@/lib/chunking'`).

- [ ] **Step 3: Écrire `chunking.ts`**

`frontend/src/lib/chunking.ts` :

```ts
import { api } from "@/lib/api";
import type {
  ChunkingConfig,
  ChunkingSpec,
  ChunkingChangeRequiresReindexBody,
} from "@/lib/chunking.types";
import type { Job } from "@/lib/workspaces.types";

const base = (name: string) => `/api/admin/workspaces/${name}/chunking-config`;

export type UpsertChunkingResult =
  | { status: "no_change" }
  | { status: "updated"; config: ChunkingConfig }
  | { status: "reindex_triggered"; job: Job };

export const chunkingApi = {
  get: (name: string) => api.get<ChunkingConfig>(base(name)),

  /**
   * PUT /chunking-config?confirm={confirm}.
   * - 204 → no_change
   * - 200 → updated (+ ChunkingConfig)
   * - 202 → reindex_triggered (+ Job)
   * - 409 propage ApiError ; le caller intercepte pour afficher le dialog.
   */
  upsert: async (
    name: string,
    payload: ChunkingSpec,
    confirm: boolean = false,
  ): Promise<UpsertChunkingResult> => {
    const url = confirm ? `${base(name)}?confirm=true` : base(name);
    const res = await api.putRaw(url, payload);
    if (res.status === 204) return { status: "no_change" };
    if (res.status === 200) {
      const config = (await res.json()) as ChunkingConfig;
      return { status: "updated", config };
    }
    if (res.status === 202) {
      const job = (await res.json()) as Job;
      return { status: "reindex_triggered", job };
    }
    throw new Error(`Unexpected status ${res.status} from PUT chunking-config`);
  },
};

export function isChunkingChangeRequiresReindex(
  body: unknown,
): body is ChunkingChangeRequiresReindexBody {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    (body as { error: unknown }).error === "chunking_change_requires_reindex"
  );
}
```

- [ ] **Step 4: Lancer (vert)**

```
cd frontend && npm test -- src/lib/__tests__/chunking.test.ts
```

Expected : 9 PASS.

- [ ] **Step 5: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/lib/chunking.ts frontend/src/lib/__tests__/chunking.test.ts
git commit -m "feat(M9b-T2): API client chunking (get/upsert) + helper isChunkingChangeRequiresReindex"
```

---

## Task 3 — Hooks `useChunkingConfig` + `useUpsertChunkingConfig` + tests

**Files:**
- Create: `frontend/src/hooks/useChunking.ts`
- Create: `frontend/src/hooks/__tests__/useChunking.test.ts`

- [ ] **Step 1: Vérifier la structure des tests sibling**

```
cat frontend/src/hooks/__tests__/useRerank.test.ts 2>/dev/null || ls frontend/src/hooks/__tests__/
```

Si pas de test sibling, le pattern à reproduire est : `@testing-library/react` + `renderHook` + `wrapper` avec `QueryClientProvider`.

- [ ] **Step 2: Écrire les tests (rouge)**

`frontend/src/hooks/__tests__/useChunking.test.ts` :

```ts
import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useChunkingConfig, useUpsertChunkingConfig } from "@/hooks/useChunking";
import { chunkingApi } from "@/lib/chunking";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

const baseSpec: ChunkingSpec = {
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
};

const baseConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  ...baseSpec,
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe("useChunkingConfig", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("fetch et retourne data sur 200", async () => {
    vi.spyOn(chunkingApi, "get").mockResolvedValue(baseConfig);
    const { result } = renderHook(() => useChunkingConfig("ws-1", true), { wrapper });
    await waitFor(() => expect(result.current.data).toBeDefined());
    expect(result.current.data?.workspace_id).toBe("ws-1");
  });

  it("ne fetch pas quand enabled=false", () => {
    const spy = vi.spyOn(chunkingApi, "get").mockResolvedValue(baseConfig);
    renderHook(() => useChunkingConfig("ws-1", false), { wrapper });
    expect(spy).not.toHaveBeenCalled();
  });
});

describe("useUpsertChunkingConfig", () => {
  beforeEach(() => vi.restoreAllMocks());

  it("invalide les queries chunking sur 'updated'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({
      status: "updated",
      config: baseConfig,
    });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: false });

    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "chunking"],
    });
  });

  it("invalide chunking + jobs sur 'reindex_triggered'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({
      status: "reindex_triggered",
      job: {
        id: "j",
        triggered_by: "reindex_chunking_change",
        status: "pending",
        files_changed: 0,
        files_skipped: 0,
        error_message: null,
        started_at: null,
        finished_at: null,
        duration_ms: null,
      },
    });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: true });

    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "chunking"],
    });
    expect(invSpy).toHaveBeenCalledWith({
      queryKey: ["workspace", "ws-1", "jobs"],
    });
  });

  it("n'invalide rien sur 'no_change'", async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invSpy = vi.spyOn(qc, "invalidateQueries");
    vi.spyOn(chunkingApi, "upsert").mockResolvedValue({ status: "no_change" });

    function customWrapper({ children }: { children: ReactNode }) {
      return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
    }

    const { result } = renderHook(() => useUpsertChunkingConfig("ws-1"), {
      wrapper: customWrapper,
    });
    await result.current.mutateAsync({ payload: baseSpec, confirm: false });

    expect(invSpy).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 3: Lancer (rouge)**

```
cd frontend && npm test -- src/hooks/__tests__/useChunking.test.ts
```

Expected : `Cannot find module '@/hooks/useChunking'`.

- [ ] **Step 4: Écrire `useChunking.ts`**

`frontend/src/hooks/useChunking.ts` :

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chunkingApi, type UpsertChunkingResult } from "@/lib/chunking";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

/**
 * Récupère la chunking_config du workspace. Config obligatoire : un workspace
 * en a toujours une (créée à l'init via M9-T6 backend).
 */
export function useChunkingConfig(name: string, enabled: boolean) {
  return useQuery<ChunkingConfig>({
    queryKey: ["workspace", name, "chunking"],
    queryFn: () => chunkingApi.get(name),
    enabled,
  });
}

type UpsertVars = { payload: ChunkingSpec; confirm: boolean };

/**
 * Upsert chunking_config. Le caller passe confirm=false au premier essai —
 * une ApiError 409 (chunking_change_requires_reindex) doit être interceptée
 * par le composant pour afficher le dialog de confirmation, qui rappellera
 * la mutation avec confirm=true.
 */
export function useUpsertChunkingConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<UpsertChunkingResult, Error, UpsertVars>({
    mutationFn: ({ payload, confirm }) =>
      chunkingApi.upsert(name, payload, confirm),
    onSuccess: (result) => {
      if (result.status !== "no_change") {
        void qc.invalidateQueries({
          queryKey: ["workspace", name, "chunking"],
        });
      }
      if (result.status === "reindex_triggered") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      }
    },
  });
}
```

- [ ] **Step 5: Lancer (vert)**

```
cd frontend && npm test -- src/hooks/__tests__/useChunking.test.ts
```

Expected : 5 PASS.

- [ ] **Step 6: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/hooks/useChunking.ts frontend/src/hooks/__tests__/useChunking.test.ts
git commit -m "feat(M9b-T3): hooks useChunkingConfig + useUpsertChunkingConfig + tests"
```

---

## Task 4 — i18n FR + EN

**Files:**
- Modify: `frontend/src/i18n/fr.json`
- Modify: `frontend/src/i18n/en.json`

- [ ] **Step 1: Repérer les clés à ajouter**

Ouvrir `frontend/src/i18n/fr.json` et localiser :
- l'entrée `tabs` au top-level
- le namespace `workspace` qui contient déjà `rerank.*`

- [ ] **Step 2: Ajouter les clés dans `fr.json`**

Au top-level, dans `tabs` :

```json
"tabs": {
  "detail": "Détail",
  "sources_one": "Source ({{count}})",
  "sources_other": "Sources ({{count}})",
  "jobs": "Jobs",
  "model": "Modèle",
  "rerank": "Rerank",
  "chunking": "Chunking"
}
```

(Ajouter `chunking` à la fin — préserver l'ordre existant pour les autres clés.)

Dans le namespace `workspace`, à la fin (avant la fermeture `}` du namespace) :

```json
"chunking": {
  "title": "Configuration du chunking",
  "badgeMandatory": "obligatoire",
  "description": "Stratégie de découpage des documents avant indexation. Modifier ces paramètres nécessite une réindexation complète du workspace.",
  "warning": "Modifier ces paramètres rend les chunks existants incohérents avec les nouveaux embeddings. Une réindexation complète sera demandée.",
  "fields": {
    "strategy": "Stratégie",
    "strategyHelp": {
      "paragraph": "Découpage par paragraphes avec coalesce des petits et split des gros."
    },
    "strategies": { "paragraph": "Paragraphes (par défaut)" },
    "maxChars": "Taille max d'un chunk (caractères)",
    "maxCharsHelp": "doit être ≥ 1",
    "minChars": "Taille min avant coalesce (caractères)",
    "minCharsHelp": "doit être < taille max",
    "overlapChars": "Overlap entre chunks (caractères)",
    "overlapCharsHelp": "doit être < taille max"
  },
  "errors": {
    "required": "Valeur requise",
    "min": "Valeur trop petite",
    "min_lt_max": "Doit être inférieur à la taille max",
    "overlap_lt_max": "Doit être inférieur à la taille max"
  },
  "actions": { "save": "Enregistrer", "cancel": "Annuler" },
  "save": {
    "success": "Configuration enregistrée",
    "noChange": "Aucune modification",
    "error": "Échec de l'enregistrement"
  },
  "reindex": {
    "triggered": "Réindexation lancée",
    "dialog": {
      "title": "Réindexation requise",
      "intro": "Cette modification nécessite de réindexer l'intégralité du workspace.",
      "labelCurrent": "Configuration actuelle :",
      "labelNew": "Nouvelle configuration :",
      "consequence": "Cette opération va supprimer tous les chunks existants et ré-indexer les documents. Cela peut prendre plusieurs minutes.",
      "actions": { "cancel": "Annuler", "confirm": "Réindexer maintenant" }
    }
  },
  "lastModified": "Dernière modification : {{when}}"
}
```

- [ ] **Step 3: Ajouter les clés équivalentes dans `en.json`**

`tabs.chunking` : `"Chunking"` (identique).

Dans le namespace `workspace.chunking` (à la fin) :

```json
"chunking": {
  "title": "Chunking configuration",
  "badgeMandatory": "mandatory",
  "description": "Document chunking strategy applied before indexing. Modifying these parameters requires a full reindexation of the workspace.",
  "warning": "Modifying these parameters makes existing chunks inconsistent with new embeddings. A full reindexation will be required.",
  "fields": {
    "strategy": "Strategy",
    "strategyHelp": {
      "paragraph": "Split by paragraphs with coalesce of small ones and split of large ones."
    },
    "strategies": { "paragraph": "Paragraphs (default)" },
    "maxChars": "Max chunk size (characters)",
    "maxCharsHelp": "must be ≥ 1",
    "minChars": "Min size before coalesce (characters)",
    "minCharsHelp": "must be < max size",
    "overlapChars": "Overlap between chunks (characters)",
    "overlapCharsHelp": "must be < max size"
  },
  "errors": {
    "required": "Required value",
    "min": "Value too small",
    "min_lt_max": "Must be less than max size",
    "overlap_lt_max": "Must be less than max size"
  },
  "actions": { "save": "Save", "cancel": "Cancel" },
  "save": {
    "success": "Configuration saved",
    "noChange": "No changes",
    "error": "Save failed"
  },
  "reindex": {
    "triggered": "Reindexation started",
    "dialog": {
      "title": "Reindexation required",
      "intro": "This modification requires reindexing the entire workspace.",
      "labelCurrent": "Current configuration:",
      "labelNew": "New configuration:",
      "consequence": "This operation will delete all existing chunks and re-index the documents. This may take several minutes.",
      "actions": { "cancel": "Cancel", "confirm": "Reindex now" }
    }
  },
  "lastModified": "Last modified: {{when}}"
}
```

- [ ] **Step 4: Vérifier la syntaxe JSON**

```
cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr.json', 'utf8'))"
cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/en.json', 'utf8'))"
```

Expected : pas de sortie (donc pas d'erreur de parse). Si erreur, identifier la virgule manquante ou en trop.

- [ ] **Step 5: Lint**

```
cd frontend && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/i18n/fr.json frontend/src/i18n/en.json
git commit -m "feat(M9b-T4): i18n FR + EN section chunking + tabs.chunking"
```

---

## Task 5 — Schema Zod `WorkspaceChunkingTab.schema.ts` + tests

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts`
- Create: `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts`

- [ ] **Step 1: Écrire les tests (rouge)**

`frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts` :

```ts
import { describe, it, expect } from "vitest";
import {
  chunkingFormSchema,
  DEFAULT_CHUNKING_FORM,
} from "@/pages/workspace/WorkspaceChunkingTab.schema";

describe("chunkingFormSchema", () => {
  it("valide les défauts", () => {
    expect(() => chunkingFormSchema.parse(DEFAULT_CHUNKING_FORM)).not.toThrow();
  });

  it("rejette max_chars < 1", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 0,
      min_chars: 0,
      overlap_chars: 0,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0].path).toContain("max_chars");
    }
  });

  it("rejette min_chars >= max_chars avec message min_lt_max", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 200,
      min_chars: 200,
      overlap_chars: 50,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path[0] === "min_chars");
      expect(issue?.message).toBe("min_lt_max");
    }
  });

  it("rejette overlap_chars >= max_chars avec message overlap_lt_max", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "paragraph",
      max_chars: 500,
      min_chars: 100,
      overlap_chars: 500,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      const issue = r.error.issues.find((i) => i.path[0] === "overlap_chars");
      expect(issue?.message).toBe("overlap_lt_max");
    }
  });

  it("accepte min_chars=0", () => {
    expect(() =>
      chunkingFormSchema.parse({
        strategy: "paragraph",
        max_chars: 1000,
        min_chars: 0,
        overlap_chars: 100,
      }),
    ).not.toThrow();
  });

  it("accepte overlap_chars=0", () => {
    expect(() =>
      chunkingFormSchema.parse({
        strategy: "paragraph",
        max_chars: 1000,
        min_chars: 100,
        overlap_chars: 0,
      }),
    ).not.toThrow();
  });

  it("coerce string → number sur max_chars", () => {
    const r = chunkingFormSchema.parse({
      strategy: "paragraph",
      max_chars: "1500" as unknown as number,
      min_chars: 100,
      overlap_chars: 100,
    });
    expect(r.max_chars).toBe(1500);
  });
});
```

- [ ] **Step 2: Lancer (rouge)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts
```

Expected : `Cannot find module …/WorkspaceChunkingTab.schema`.

- [ ] **Step 3: Écrire le schema**

`frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` :

```ts
import { z } from "zod";
import type { ChunkingStrategy } from "@/lib/chunking.types";

export const CHUNKING_STRATEGIES: ChunkingStrategy[] = ["paragraph"];

export const chunkingFormSchema = z
  .object({
    strategy: z.enum(["paragraph"]),
    max_chars: z.coerce.number().int().min(1, "min"),
    min_chars: z.coerce.number().int().min(0, "min"),
    overlap_chars: z.coerce.number().int().min(0, "min"),
  })
  .superRefine((data, ctx) => {
    if (data.min_chars >= data.max_chars) {
      ctx.addIssue({
        path: ["min_chars"],
        code: z.ZodIssueCode.custom,
        message: "min_lt_max",
      });
    }
    if (data.overlap_chars >= data.max_chars) {
      ctx.addIssue({
        path: ["overlap_chars"],
        code: z.ZodIssueCode.custom,
        message: "overlap_lt_max",
      });
    }
  });

export type ChunkingFormValues = z.infer<typeof chunkingFormSchema>;

export const DEFAULT_CHUNKING_FORM: ChunkingFormValues = {
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
};
```

- [ ] **Step 4: Lancer (vert)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts
```

Expected : 7 PASS.

- [ ] **Step 5: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts
git commit -m "feat(M9b-T5): schema Zod chunking + tests validations"
```

---

## Task 6 — `ChunkingConfirmReindexAlert` + tests

**Files:**
- Create: `frontend/src/pages/workspace/ChunkingConfirmReindexAlert.tsx`
- Create: `frontend/src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx`

- [ ] **Step 1: Écrire les tests (rouge)**

`frontend/src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx` :

```tsx
import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { ChunkingConfirmReindexAlert } from "@/pages/workspace/ChunkingConfirmReindexAlert";

describe("ChunkingConfirmReindexAlert", () => {
  it("ne rend rien quand open=false", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={false}
        onOpenChange={() => {}}
        current="paragraph (max=2000, min=200, overlap=200)"
        next="paragraph (max=1500, min=100, overlap=150)"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    expect(screen.queryByText(/Réindexation requise/i)).not.toBeInTheDocument();
  });

  it("affiche current et next quand open=true", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="paragraph (max=2000, min=200, overlap=200)"
        next="paragraph (max=1500, min=100, overlap=150)"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    expect(screen.getByText(/Réindexation requise/i)).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=2000, min=200, overlap=200)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=1500, min=100, overlap=150)"),
    ).toBeInTheDocument();
  });

  it("appelle onConfirm au clic Réindexer maintenant", () => {
    const onConfirm = vi.fn();
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="a"
        next="b"
        onConfirm={onConfirm}
        pending={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /Réindexer maintenant/i }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("appelle onOpenChange(false) au clic Annuler", () => {
    const onOpenChange = vi.fn();
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={onOpenChange}
        current="a"
        next="b"
        onConfirm={() => {}}
        pending={false}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: /^Annuler$/i }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("désactive Réindexer maintenant quand pending=true", () => {
    renderWithProviders(
      <ChunkingConfirmReindexAlert
        open={true}
        onOpenChange={() => {}}
        current="a"
        next="b"
        onConfirm={() => {}}
        pending={true}
      />,
    );
    expect(
      screen.getByRole("button", { name: /Réindexer maintenant/i }),
    ).toBeDisabled();
  });
});
```

- [ ] **Step 2: Lancer (rouge)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx
```

Expected : `Cannot find module …/ChunkingConfirmReindexAlert`.

- [ ] **Step 3: Écrire le composant**

`frontend/src/pages/workspace/ChunkingConfirmReindexAlert.tsx` :

```tsx
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

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  current: string;
  next: string;
  onConfirm: () => void;
  pending: boolean;
}

export function ChunkingConfirmReindexAlert({
  open,
  onOpenChange,
  current,
  next,
  onConfirm,
  pending,
}: Props) {
  const { t } = useTranslation("workspace");

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            {t("chunking.reindex.dialog.title")}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2 text-sm">
              <p>{t("chunking.reindex.dialog.intro")}</p>
              <p>
                <span className="font-medium">
                  {t("chunking.reindex.dialog.labelCurrent")}
                </span>
                <br />
                <span className="font-mono text-slate-700">{current}</span>
              </p>
              <p>
                <span className="font-medium">
                  {t("chunking.reindex.dialog.labelNew")}
                </span>
                <br />
                <span className="font-mono text-slate-700">{next}</span>
              </p>
              <p className="text-slate-500">
                {t("chunking.reindex.dialog.consequence")}
              </p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>
            {t("chunking.reindex.dialog.actions.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={pending}
            className="bg-amber-600 hover:bg-amber-700"
          >
            {t("chunking.reindex.dialog.actions.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 4: Lancer (vert)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx
```

Expected : 5 PASS.

- [ ] **Step 5: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/workspace/ChunkingConfirmReindexAlert.tsx frontend/src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx
git commit -m "feat(M9b-T6): ChunkingConfirmReindexAlert (AlertDialog) + tests"
```

---

## Task 7 — `WorkspaceChunkingTab` + tests

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx`
- Create: `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx`

- [ ] **Step 1: Écrire les tests (rouge)**

`frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx` :

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceChunkingTab } from "@/pages/workspace/WorkspaceChunkingTab";
import type { Workspace } from "@/lib/workspaces.types";
import type { ChunkingConfig } from "@/lib/chunking.types";
import { ApiError } from "@/lib/api";

const upsertMutate = vi.fn();

vi.mock("@/hooks/useChunking", () => ({
  useChunkingConfig: vi.fn(),
  useUpsertChunkingConfig: () => ({ mutate: upsertMutate, isPending: false }),
}));

const toastMock = vi.fn();
vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

import { useChunkingConfig } from "@/hooks/useChunking";

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

const mockConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

function mockState(data: ChunkingConfig | undefined, isLoading = false) {
  vi.mocked(useChunkingConfig).mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useChunkingConfig>);
}

describe("WorkspaceChunkingTab", () => {
  beforeEach(() => {
    upsertMutate.mockReset();
    toastMock.mockReset();
  });

  it("affiche LoadingSpinner pendant le fetch", () => {
    mockState(undefined, true);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    // Pas de form
    expect(screen.queryByText(/Configuration du chunking/i)).not.toBeInTheDocument();
  });

  it("rend le form pré-rempli avec la config actuelle", () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByText(/Configuration du chunking/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("2000")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("200")).toHaveLength(2); // min + overlap
  });

  it("bouton Enregistrer disabled tant que form clean", () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByRole("button", { name: /^Enregistrer$/i })).toBeDisabled();
  });

  it("submit déclenche upsert avec confirm=false", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    // Modifier max_chars
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs).toMatchObject({
      payload: expect.objectContaining({ max_chars: 1500 }),
      confirm: false,
    });
  });

  it("toast noChange sur status no_change", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    // Simuler la réponse no_change
    callbacks.onSuccess({ status: "no_change" });

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/Aucune modification/i) }),
      ),
    );
  });

  it("toast success sur status updated", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    callbacks.onSuccess({
      status: "updated",
      config: { ...mockConfig, max_chars: 1500 },
    });

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/Configuration enregistrée/i) }),
      ),
    );
  });

  it("ouvre le dialog 409 avec current/new sur ApiError(409)", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    callbacks.onError(
      new ApiError(409, {
        error: "chunking_change_requires_reindex",
        workspace: "my-workspace",
        current: "paragraph (max=2000, min=200, overlap=200)",
        new: "paragraph (max=1500, min=200, overlap=200)",
        action: "PUT /workspaces/my-workspace/chunking-config?confirm=true",
      }),
    );

    await waitFor(() =>
      expect(screen.getByText(/Réindexation requise/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText("paragraph (max=2000, min=200, overlap=200)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=1500, min=200, overlap=200)"),
    ).toBeInTheDocument();
  });

  it("clic Réindexer maintenant déclenche 2ᵉ upsert avec confirm=true", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    upsertMutate.mock.calls[0]?.[1].onError(
      new ApiError(409, {
        error: "chunking_change_requires_reindex",
        workspace: "my-workspace",
        current: "paragraph (max=2000, min=200, overlap=200)",
        new: "paragraph (max=1500, min=200, overlap=200)",
        action: "PUT /workspaces/my-workspace/chunking-config?confirm=true",
      }),
    );

    await waitFor(() => screen.getByText(/Réindexation requise/i));
    fireEvent.click(screen.getByRole("button", { name: /Réindexer maintenant/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalledTimes(2));
    const secondCall = upsertMutate.mock.calls[1]?.[0];
    expect(secondCall).toMatchObject({ confirm: true });
  });

  it("erreur Zod min ≥ max → message d'erreur, pas de submit", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const inputs = screen.getAllByDisplayValue("200");
    // min_chars = 3000
    fireEvent.change(inputs[0], { target: { value: "3000" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Doit être inférieur à la taille max/i),
      ).toBeInTheDocument();
    });
    expect(upsertMutate).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Lancer (rouge)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx
```

Expected : `Cannot find module …/WorkspaceChunkingTab`.

- [ ] **Step 3: Écrire le composant**

`frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` :

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
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
import { useChunkingConfig, useUpsertChunkingConfig } from "@/hooks/useChunking";
import { ApiError } from "@/lib/api";
import { isChunkingChangeRequiresReindex } from "@/lib/chunking";
import type { UpsertChunkingResult } from "@/lib/chunking";
import type { ChunkingSpec, ChunkingStrategy } from "@/lib/chunking.types";
import type { Workspace } from "@/lib/workspaces.types";
import { ChunkingConfirmReindexAlert } from "./ChunkingConfirmReindexAlert";
import {
  CHUNKING_STRATEGIES,
  chunkingFormSchema,
  DEFAULT_CHUNKING_FORM,
  type ChunkingFormValues,
} from "./WorkspaceChunkingTab.schema";

function relativeTimeRaw(iso: string): { key: string; count: number } {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return { key: "time.justNow", count: 0 };
  if (m < 60) return { key: "time.minutesAgo", count: m };
  const h = Math.floor(m / 60);
  if (h < 24) return { key: "time.hoursAgo", count: h };
  return { key: "time.daysAgo", count: Math.floor(h / 24) };
}

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceChunkingTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data, isLoading } = useChunkingConfig(workspace.name, enabled);
  const upsert = useUpsertChunkingConfig(workspace.name);
  const [confirmReindex, setConfirmReindex] = useState<{
    payload: ChunkingSpec;
    current: string;
    next: string;
  } | null>(null);

  const form = useForm<ChunkingFormValues>({
    resolver: zodResolver(chunkingFormSchema),
    defaultValues: DEFAULT_CHUNKING_FORM,
  });

  useEffect(() => {
    if (data) {
      form.reset({
        strategy: data.strategy,
        max_chars: data.max_chars,
        min_chars: data.min_chars,
        overlap_chars: data.overlap_chars,
      });
    }
  }, [data, form]);

  const handleUpsertResult = (result: UpsertChunkingResult) => {
    if (result.status === "no_change") {
      toast({ title: t("chunking.save.noChange") });
    } else if (result.status === "updated") {
      toast({ title: t("chunking.save.success") });
      form.reset({
        strategy: result.config.strategy,
        max_chars: result.config.max_chars,
        min_chars: result.config.min_chars,
        overlap_chars: result.config.overlap_chars,
      });
    } else {
      toast({ title: t("chunking.reindex.triggered") });
      // form reset après reindex_triggered : on prend les valeurs soumises
      form.reset(form.getValues());
    }
  };

  const onSubmit = (values: ChunkingFormValues) => {
    const payload: ChunkingSpec = { ...values, extras: {} };
    upsert.mutate(
      { payload, confirm: false },
      {
        onSuccess: handleUpsertResult,
        onError: (err) => {
          if (
            err instanceof ApiError &&
            err.status === 409 &&
            isChunkingChangeRequiresReindex(err.body)
          ) {
            setConfirmReindex({
              payload,
              current: err.body.current,
              next: err.body.new,
            });
            return;
          }
          toast({ title: t("chunking.save.error"), variant: "destructive" });
        },
      },
    );
  };

  const onConfirmReindex = () => {
    if (!confirmReindex) return;
    upsert.mutate(
      { payload: confirmReindex.payload, confirm: true },
      {
        onSuccess: (result) => {
          setConfirmReindex(null);
          handleUpsertResult(result);
        },
        onError: () => {
          setConfirmReindex(null);
          toast({ title: t("chunking.save.error"), variant: "destructive" });
        },
      },
    );
  };

  if (isLoading || !data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          {t("chunking.title")}
          <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-slate-600">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            {t("chunking.badgeMandatory")}
          </span>
        </h3>
        <p className="mt-1 text-sm text-slate-600">{t("chunking.description")}</p>
      </div>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4 rounded-md border bg-white p-4"
      >
        {/* Stratégie */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.strategy")}
          </label>
          <Controller
            name="strategy"
            control={form.control}
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(v) => field.onChange(v as ChunkingStrategy)}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CHUNKING_STRATEGIES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {t(`chunking.fields.strategies.${s}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <p className="mt-1 text-xs text-slate-500">
            {t(`chunking.fields.strategyHelp.${form.watch("strategy")}`)}
          </p>
        </div>

        {/* max_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.maxChars")}
          </label>
          <Input
            type="number"
            min={1}
            {...form.register("max_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.maxCharsHelp")}
          </p>
          {form.formState.errors.max_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.max_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        {/* min_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.minChars")}
          </label>
          <Input
            type="number"
            min={0}
            {...form.register("min_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.minCharsHelp")}
          </p>
          {form.formState.errors.min_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.min_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        {/* overlap_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.overlapChars")}
          </label>
          <Input
            type="number"
            min={0}
            {...form.register("overlap_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.overlapCharsHelp")}
          </p>
          {form.formState.errors.overlap_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.overlap_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        <p className="text-xs text-slate-500">
          {(() => {
            const rt = relativeTimeRaw(data.updated_at);
            const when =
              rt.key === "time.justNow"
                ? t("time.justNow")
                : t(rt.key, { count: rt.count });
            return t("chunking.lastModified", { when });
          })()}
        </p>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              form.reset({
                strategy: data.strategy,
                max_chars: data.max_chars,
                min_chars: data.min_chars,
                overlap_chars: data.overlap_chars,
              })
            }
            disabled={!form.formState.isDirty}
          >
            {t("chunking.actions.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={!form.formState.isDirty || upsert.isPending}
          >
            {t("chunking.actions.save")}
          </Button>
        </div>
      </form>

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("chunking.warning")}</p>
      </div>

      {confirmReindex && (
        <ChunkingConfirmReindexAlert
          open={true}
          onOpenChange={(o) => {
            if (!o) setConfirmReindex(null);
          }}
          current={confirmReindex.current}
          next={confirmReindex.next}
          onConfirm={onConfirmReindex}
          pending={upsert.isPending}
        />
      )}
    </div>
  );
}
```

- [ ] **Step 4: Lancer (vert)**

```
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx
```

Expected : 9 PASS.

- [ ] **Step 5: TypeScript + lint**

```
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceChunkingTab.tsx frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx
git commit -m "feat(M9b-T7): WorkspaceChunkingTab (form + 4 branches PUT) + tests"
```

---

## Task 8 — Intégration dans `WorkspaceDetailPanel` + smoke final

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`
- Modify: `specs/09-roadmap.md`

- [ ] **Step 1: Modifier `WorkspaceDetailPanel.tsx`**

Ajouter l'import :

```tsx
import { WorkspaceChunkingTab } from "./WorkspaceChunkingTab";
```

Dans la `TabsList`, après `rerank` :

```tsx
<TabsTrigger value="chunking">{t("tabs.chunking")}</TabsTrigger>
```

Après le `TabsContent value="rerank"`, ajouter :

```tsx
<TabsContent value="chunking" className="pt-4">
  <WorkspaceChunkingTab workspace={ws} enabled={activeTab === "chunking"} />
</TabsContent>
```

- [ ] **Step 2: Lancer la suite complète frontend**

```
cd frontend && npx tsc --noEmit && npm run lint && npm test
```

Expected : tous les tests passent, aucune erreur TypeScript ni lint.

- [ ] **Step 3: Smoke manuel (optionnel mais recommandé)**

```
cd frontend && npm run dev
```

Visiter `http://localhost:5173`, ouvrir un workspace, cliquer sur l'onglet `Chunking`, vérifier :
- Le form est pré-rempli avec la config courante
- Modifier `max_chars` → cliquer `Enregistrer` → toast affiché
- Sur un workspace avec documents indexés : modifier puis enregistrer → dialog `Réindexation requise` s'affiche avec `current` et `next` corrects
- Cliquer `Réindexer maintenant` → toast `Réindexation lancée`
- Onglet `Jobs` : nouveau job `reindex_chunking_change` en `pending`

Killer `npm run dev` après vérification.

- [ ] **Step 4: Mettre à jour la roadmap**

Modifier `specs/09-roadmap.md` § « Amélioration du chunking » :

Remplacer la section actuelle (qui dit "Frontend dédié différé en M9b") par :

```markdown
### Amélioration du chunking

✅ Infrastructure backend livrée en M9 — cf. `docs/superpowers/specs/2026-05-18-M9-backend-chunking-infrastructure-design.md`.
✅ Frontend livré en M9b — onglet `Chunking` dans `WorkspaceDetailPanel`, cf. `docs/superpowers/specs/2026-05-19-M9b-frontend-chunking-design.md`.

Pattern factory + registry par stratégie côté backend, config par workspace (table `chunking_configs`), champ `embeddings.metadata jsonb` prêt, runner de migrations workspace au boot. Une seule stratégie disponible : `paragraph` (algo historique).

Stratégies futures (jalons distincts) :
- Chunking sémantique (respect des sections Markdown)
- Chunking par blocs de code
- Métadonnées de chunk enrichies (titre de section parent, type de contenu)
```

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceDetailPanel.tsx specs/09-roadmap.md
git commit -m "feat(M9b-T8): integration onglet Chunking dans WorkspaceDetailPanel + roadmap"
```

---

## Self-review du plan

1. **Couverture spec** :
   - §3 inventaire des fichiers → Task 1 + 2 + 3 + 5 + 6 + 7 + 8 (tous présents)
   - §4 types & API client → Task 1 (types, putRaw, Job extension) + Task 2 (chunking.ts)
   - §5 hooks → Task 3
   - §6 composants UI → Task 5 (schema), Task 6 (ConfirmAlert), Task 7 (Tab)
   - §7 i18n → Task 4
   - §8 error handling matrix → couvert par les 4 branches du Task 7 (no_change, updated, reindex_triggered, 409 → dialog)
   - §9 accessibilité → AlertDialog shadcn (focus trap natif), labels htmlFor sur Inputs, classes amber-600 sur "Réindexer maintenant"
   - §10 tests → Tasks 2/3/5/6/7 (chacun rouge → impl → vert)
   - §11 plan de livraison → 8 tasks alignées
   - §12 risques → mitigés (`api.putRaw` ajouté en Task 1, helper colocale, `confirmReindex` state cleanup, `isPending` désactive le bouton)

2. **Aucun placeholder** : tous les blocs de code sont complets. Quelques messages d'i18n en JSON imbriqué montrés en entier.

3. **Cohérence des types** :
   - `ChunkingConfig`, `ChunkingSpec`, `ChunkingStrategy` cohérents entre Task 1 (déclaration), Task 2 (chunking.ts), Task 3 (hooks), Task 5 (schema), Task 7 (composant)
   - `UpsertChunkingResult` discriminé : `{status: "no_change"}` | `{status: "updated", config}` | `{status: "reindex_triggered", job}` — utilisé identiquement partout
   - `ChunkingChangeRequiresReindexBody` : kw `error`, `workspace`, `current`, `new`, `action` — cohérent avec spec backend §5.2
   - `Job` importé depuis `@/lib/workspaces.types` (pas un nouveau type, juste extension de `triggered_by`)
   - `isChunkingChangeRequiresReindex(body): body is ChunkingChangeRequiresReindexBody` — typeguard utilisé dans Task 7

4. **Pas de Critical / Important / Minor identifié à l'auto-review.**
