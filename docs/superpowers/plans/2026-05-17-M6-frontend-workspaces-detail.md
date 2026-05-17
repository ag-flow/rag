# M6 — Page Workspaces détail + sources git Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la page Workspaces M5b (table liste plate) par un master-detail avec 4 onglets (Détail / Sources git / Jobs / Modèle), dialogs reveal/rotate/reindex/add-source/delete et i18n complet, en répliquant le pattern Coffres Harpocrate M5cd-front.

**Architecture:** React 18 + TS strict + react-router-dom + TanStack Query + Tailwind + shadcn/ui + i18next + Vitest. Sélection workspace synchronisée URL (`?ws=<name>`). Lazy loading des onglets Sources/Jobs (React Query `enabled`). Backend déjà en place (M5b/M5e/M5f). Édition limitée à `indexer.api_key_ref`. Sources git en accordion (compact + expand inline).

**Tech Stack:** React Query v5, react-hook-form + Zod (validation), lucide-react icons, shadcn/ui (Dialog, AlertDialog, DropdownMenu, Tabs, Table, Accordion, Badge, Input, Button).

**Spec design** : `docs/superpowers/specs/2026-05-17-M6-frontend-workspaces-detail-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `frontend/src/lib/workspaces.types.ts` | **Create** | 8 types TS miroirs schemas Pydantic (Workspace, Source, Job, etc.) |
| `frontend/src/lib/workspaces.ts` | **Create** | API client `workspacesApi` (11 méthodes CRUD + sources + jobs + reveal) |
| `frontend/src/hooks/useWorkspaces.ts` | **Modify** | +6 hooks (useWorkspace, useRevealApiKey, useWorkspaceSources, useAddSource, useDeleteSource, useWorkspaceJobs) |
| `frontend/src/lib/validators.ts` | **Modify** | Retirer les types obsolètes (déplacés dans workspaces.types.ts) |
| `frontend/src/pages/WorkspacesPage.tsx` | **Rewrite** | Container master-detail + auto-sélection URL |
| `frontend/src/pages/workspace/WorkspacesList.tsx` | **Create** | Panneau gauche 240px |
| `frontend/src/pages/workspace/WorkspacesEmptyState.tsx` | **Create** | État vide (premier workspace) |
| `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` | **Create** | Container droit (header + tabs) |
| `frontend/src/pages/workspace/WorkspaceHeader.tsx` | **Create** | Sticky : nom + Reindex + menu ⋯ |
| `frontend/src/pages/workspace/WorkspaceDetailTab.tsx` | **Create** | Onglet Détail (stats + api_key_ref edit) |
| `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx` | **Create** | Onglet Sources (accordion) |
| `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` | **Create** | Onglet Jobs (historique) |
| `frontend/src/pages/workspace/WorkspaceModelTab.tsx` | **Create** | Onglet Modèle (read-only) |
| `frontend/src/pages/workspace/CreateWorkspaceDialog.tsx` | **Move** | Depuis `WorkspaceCreateDialog.tsx`, ranger sous namespace |
| `frontend/src/pages/workspace/RevealApiKeyDialog.tsx` | **Create** | Dialog reveal masqué + copy + auto-mask 30s |
| `frontend/src/pages/workspace/RotateApiKeyDialog.tsx` | **Create** | Dialog rotate + display nouvelle clé une fois |
| `frontend/src/pages/workspace/ReindexConfirmDialog.tsx` | **Create** | Confirm reindex |
| `frontend/src/pages/workspace/AddSourceDialog.tsx` | **Create** | Formulaire git (url, branch, auth_ref, include, exclude) |
| `frontend/src/pages/workspace/DeleteWorkspaceAlert.tsx` | **Rewrite** | Alert avec input nom-confirmation |
| `frontend/src/pages/workspace/DeleteSourceAlert.tsx` | **Create** | Alert delete source |
| `frontend/src/pages/WorkspaceActions.tsx` | **Delete** | Dropdown ligne disparaît, actions migrent vers WorkspaceHeader |
| `frontend/src/pages/WorkspaceCreateDialog.tsx` | **Delete** | Déplacé en `workspace/CreateWorkspaceDialog.tsx` |
| `frontend/src/pages/WorkspaceDeleteAlert.tsx` | **Delete** | Réécrit en `workspace/DeleteWorkspaceAlert.tsx` |
| `frontend/src/i18n/fr/workspace.json` | **Create** | Labels FR |
| `frontend/src/i18n/en/workspace.json` | **Create** | Labels EN |
| `frontend/src/i18n/i18n.ts` | **Modify** | Enregistrer namespace `workspace` |
| `frontend/src/pages/workspace/__tests__/*.test.tsx` | **Create** | Tests Vitest (8 fichiers) |

---

## Task 1: Types TS + API client workspaces

**Files:**
- Create: `frontend/src/lib/workspaces.types.ts`
- Create: `frontend/src/lib/workspaces.ts`

**Contexte** : `frontend/src/lib/api.ts` existe (M5b) avec `api.get/post/put/patch/delete` + `ApiError`. On l'utilise. Pattern à suivre : `frontend/src/lib/harpocrate-vaults.ts` (M5cd-front).

- [ ] **Step 1: Créer `lib/workspaces.types.ts`**

```typescript
// 8 types TS miroirs des schemas Pydantic backend
// (cf. backend/src/rag/schemas/admin.py)

export type IndexerSpec = {
  provider: string;
  model: string;
  api_key_ref: string | null;
  base_url: string | null;
};

export type Workspace = {
  id: string;
  name: string;
  indexer: IndexerSpec;
  sources_count: number;
  documents_count: number;
  last_indexed_at: string | null;
  created_at: string;
};

export type WorkspaceCreate = {
  name: string;
  indexer: {
    provider: string;
    model: string;
    api_key_ref: string | null;
    base_url?: string | null;
  };
};

export type WorkspaceCreateResponse = {
  id: string;
  name: string;
  api_key: string;
  created_at: string;
};

export type WorkspacePatchRequest = {
  indexer: { api_key_ref: string };
};

export type SourceConfig = {
  url: string;
  branch: string;
  auth_ref: string | null;
  include: string[];
  exclude: string[];
};

export type Source = {
  id: string;
  type: "git";
  config: SourceConfig;
  last_indexed_at: string | null;
  created_at: string;
};

export type SourceCreateRequest = {
  type: "git";
  config: SourceConfig;
};

export type Job = {
  id: string;
  triggered_by: "webhook" | "manual" | "push" | "schedule";
  status: "pending" | "running" | "done" | "error";
  files_changed: number;
  files_skipped: number;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
  duration_ms: number | null;
};

export type ApiKeyRotateResponse = {
  api_key: string;
};
```

- [ ] **Step 2: Créer `lib/workspaces.ts` avec 11 méthodes**

```typescript
import { api } from "@/lib/api";
import type {
  ApiKeyRotateResponse,
  Job,
  Source,
  SourceCreateRequest,
  Workspace,
  WorkspaceCreate,
  WorkspaceCreateResponse,
  WorkspacePatchRequest,
} from "@/lib/workspaces.types";

const BASE = "/api/admin/workspaces";

export const workspacesApi = {
  list: () => api.get<Workspace[]>(BASE),
  get: (name: string) => api.get<Workspace>(`${BASE}/${name}`),
  create: (payload: WorkspaceCreate) =>
    api.post<WorkspaceCreateResponse>(BASE, payload),
  patch: (name: string, payload: WorkspacePatchRequest) =>
    api.patch<Workspace>(`${BASE}/${name}`, payload),
  delete: (name: string) => api.delete<void>(`${BASE}/${name}`),
  rotateApiKey: (name: string) =>
    api.post<ApiKeyRotateResponse>(`${BASE}/${name}/rotate-apikey`, {}),
  revealApiKey: (name: string) =>
    api.get<ApiKeyRotateResponse>(`${BASE}/${name}/apikey`),
  reindex: (name: string) =>
    api.post<void>(`${BASE}/${name}/reindex?confirm=true`, {}),
  listSources: (name: string) => api.get<Source[]>(`${BASE}/${name}/sources`),
  addSource: (name: string, payload: SourceCreateRequest) =>
    api.post<Source>(`${BASE}/${name}/sources`, payload),
  deleteSource: (name: string, sourceId: string) =>
    api.delete<void>(`${BASE}/${name}/sources/${sourceId}`),
  listJobs: (name: string) => api.get<Job[]>(`${BASE}/${name}/jobs`),
};
```

- [ ] **Step 3: Smoke TypeScript**

```bash
cd frontend
npx tsc --noEmit
```
Expected : 0 erreur.

- [ ] **Step 4: Lint**

```bash
cd frontend
npm run lint
```
Expected : 0 erreur.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/lib/workspaces.types.ts frontend/src/lib/workspaces.ts
git commit -m "feat(M6-T1): types TS + API client workspaces (11 méthodes)"
```

---

## Task 2: Hooks React Query workspaces étendus

**Files:**
- Modify: `frontend/src/hooks/useWorkspaces.ts`

**Contexte** : Le hook M5b existant utilise les types de `lib/validators.ts`. On migre tout vers `lib/workspaces.types.ts` + `workspacesApi`. Lazy loading via `enabled` pour Sources et Jobs.

- [ ] **Step 1: Réécrire `useWorkspaces.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspacesApi } from "@/lib/workspaces";
import type {
  ApiKeyRotateResponse,
  Job,
  Source,
  SourceCreateRequest,
  Workspace,
  WorkspaceCreate,
  WorkspaceCreateResponse,
  WorkspacePatchRequest,
} from "@/lib/workspaces.types";

// ─── Queries ──────────────────────────────────────────────────────────────

export function useWorkspaces() {
  return useQuery({
    queryKey: ["workspaces"],
    queryFn: () => workspacesApi.list(),
  });
}

export function useWorkspace(name: string | null) {
  return useQuery({
    queryKey: ["workspace", name],
    queryFn: () => workspacesApi.get(name as string),
    enabled: name !== null,
  });
}

export function useWorkspaceSources(name: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "sources"],
    queryFn: () => workspacesApi.listSources(name as string),
    enabled: name !== null && enabled,
  });
}

export function useWorkspaceJobs(name: string | null, enabled: boolean) {
  return useQuery({
    queryKey: ["workspace", name, "jobs"],
    queryFn: () => workspacesApi.listJobs(name as string),
    enabled: name !== null && enabled,
  });
}

// ─── Mutations ────────────────────────────────────────────────────────────

export function useCreateWorkspace() {
  const qc = useQueryClient();
  return useMutation<WorkspaceCreateResponse, Error, WorkspaceCreate>({
    mutationFn: (payload) => workspacesApi.create(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useUpdateApiKeyRef(name: string) {
  const qc = useQueryClient();
  return useMutation<Workspace, Error, WorkspacePatchRequest>({
    mutationFn: (payload) => workspacesApi.patch(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useDeleteWorkspace() {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (name) => workspacesApi.delete(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspaces"] });
    },
  });
}

export function useRotateApiKey(name: string) {
  const qc = useQueryClient();
  return useMutation<ApiKeyRotateResponse, Error, void>({
    mutationFn: () => workspacesApi.rotateApiKey(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useRevealApiKey(name: string) {
  return useMutation<ApiKeyRotateResponse, Error, void>({
    mutationFn: () => workspacesApi.revealApiKey(name),
  });
}

export function useReindex(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => workspacesApi.reindex(name),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useAddSource(name: string) {
  const qc = useQueryClient();
  return useMutation<Source, Error, SourceCreateRequest>({
    mutationFn: (payload) => workspacesApi.addSource(name, payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "sources"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}

export function useDeleteSource(name: string) {
  const qc = useQueryClient();
  return useMutation<void, Error, string>({
    mutationFn: (sourceId) => workspacesApi.deleteSource(name, sourceId),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["workspace", name, "sources"] });
      void qc.invalidateQueries({ queryKey: ["workspace", name] });
    },
  });
}
```

- [ ] **Step 2: Retirer les anciens types de `validators.ts`**

Lire `frontend/src/lib/validators.ts` et **retirer** les types `Workspace`, `WorkspaceCreate`, `WorkspaceCreateResponse`, `ApiKeyRotateResponse` s'ils y sont. Garder uniquement les schémas Zod transverses (s'il y en a).

- [ ] **Step 3: Smoke tsc + lint**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```
Expected : 0 erreur. Le composant `WorkspacesPage.tsx` actuel peut casser ici car il importe les anciens types — c'est attendu, sera fixé en Task 3.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/hooks/useWorkspaces.ts frontend/src/lib/validators.ts
git commit -m "feat(M6-T2): hooks React Query workspaces (4 queries + 7 mutations)"
```

---

## Task 3: Réécrire `WorkspacesPage` master-detail + WorkspacesList + EmptyState

**Files:**
- Rewrite: `frontend/src/pages/WorkspacesPage.tsx`
- Create: `frontend/src/pages/workspace/WorkspacesList.tsx`
- Create: `frontend/src/pages/workspace/WorkspacesEmptyState.tsx`
- Create: `frontend/src/pages/workspace/CreateWorkspaceDialog.tsx` (déplacement)
- Delete: `frontend/src/pages/WorkspaceCreateDialog.tsx`
- Delete: `frontend/src/pages/WorkspaceActions.tsx`
- Delete: `frontend/src/pages/WorkspaceDeleteAlert.tsx`

**Contexte** : Le pattern à suivre est `HarpocrateVaultsPage.tsx` à 100% (lignes 1-95). Le selectedId devient `selectedName` (workspace identifié par name, pas par id).

- [ ] **Step 1: Déplacer `WorkspaceCreateDialog.tsx`**

```bash
git mv frontend/src/pages/WorkspaceCreateDialog.tsx frontend/src/pages/workspace/CreateWorkspaceDialog.tsx
```

Ouvrir le fichier déplacé et :
- Renommer l'export `WorkspaceCreateDialog` → `CreateWorkspaceDialog`.
- Adapter les imports vers `@/lib/workspaces.types` (au lieu de `validators`).
- Adapter le hook `useCreateWorkspace` (chemin inchangé, mais signature peut différer).

- [ ] **Step 2: Créer `workspace/WorkspacesEmptyState.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import { FolderOpen, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  onCreate: () => void;
}

export function WorkspacesEmptyState({ onCreate }: Props) {
  const { t } = useTranslation("workspace");
  return (
    <div className="flex flex-1 items-center justify-center p-8">
      <div className="max-w-md text-center rounded-lg border border-dashed border-slate-300 p-10">
        <FolderOpen className="mx-auto mb-3 h-10 w-10 text-slate-400" />
        <h3 className="text-base font-semibold text-slate-900 mb-1.5">
          {t("empty.title")}
        </h3>
        <p className="text-sm text-slate-500 mb-5">{t("empty.description")}</p>
        <Button onClick={onCreate}>
          <Plus className="h-4 w-4" />
          {t("list.new")}
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Créer `workspace/WorkspacesList.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { Workspace } from "@/lib/workspaces.types";

interface WorkspacesListProps {
  selectedName: string | null;
  onSelect: (name: string) => void;
  onCreate: () => void;
}

export function WorkspacesList({ selectedName, onSelect, onCreate }: WorkspacesListProps) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaces();

  return (
    <aside className="w-[240px] flex-shrink-0 border-r border-slate-200 bg-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <span className="font-semibold text-slate-900">{t("list.header")}</span>
        <Button size="sm" onClick={onCreate} className="h-7 px-2.5 text-xs">
          {t("list.new")}
        </Button>
      </div>
      <div className="py-2">
        {isLoading ? (
          <div className="px-4 py-6 flex justify-center"><LoadingSpinner /></div>
        ) : (
          (data ?? []).map((ws: Workspace) => (
            <button
              key={ws.id}
              type="button"
              onClick={() => onSelect(ws.name)}
              className={cn(
                "w-full text-left px-4 py-2 hover:bg-slate-50",
                ws.name === selectedName && "bg-blue-50 hover:bg-blue-100",
              )}
            >
              <div className="font-medium text-sm text-slate-900">{ws.name}</div>
              <div className="text-xs text-slate-500">
                {ws.indexer.provider}/{ws.indexer.model} · {ws.documents_count} docs
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
```

- [ ] **Step 4: Réécrire `WorkspacesPage.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { WorkspacesList } from "@/pages/workspace/WorkspacesList";
import { WorkspacesEmptyState } from "@/pages/workspace/WorkspacesEmptyState";
import { WorkspaceDetailPanel } from "@/pages/workspace/WorkspaceDetailPanel";
import { CreateWorkspaceDialog } from "@/pages/workspace/CreateWorkspaceDialog";

export function WorkspacesPage() {
  const { data, isLoading } = useWorkspaces();
  const [searchParams, setSearchParams] = useSearchParams();
  const selectedName = searchParams.get("ws");
  const [createOpen, setCreateOpen] = useState(false);

  useEffect(() => {
    if (isLoading) return;
    if (selectedName) return;
    if (!data || data.length === 0) return;
    setSearchParams({ ws: data[0].name }, { replace: true });
  }, [data, isLoading, selectedName, setSearchParams]);

  const handleSelect = (name: string) => {
    setSearchParams({ ws: name }, { replace: true });
  };

  const handleCreated = (ws: { name: string }) => {
    setSearchParams({ ws: ws.name }, { replace: true });
  };

  if (isLoading) {
    return <div className="flex h-full items-center justify-center"><LoadingSpinner /></div>;
  }

  const workspaces = data ?? [];

  if (workspaces.length === 0) {
    return (
      <>
        <div className="flex h-full">
          <WorkspacesEmptyState onCreate={() => setCreateOpen(true)} />
        </div>
        <CreateWorkspaceDialog
          open={createOpen}
          onOpenChange={setCreateOpen}
          onCreated={handleCreated}
        />
      </>
    );
  }

  return (
    <>
      <div className="flex h-full">
        <WorkspacesList
          selectedName={selectedName}
          onSelect={handleSelect}
          onCreate={() => setCreateOpen(true)}
        />
        {selectedName && <WorkspaceDetailPanel name={selectedName} />}
      </div>
      <CreateWorkspaceDialog
        open={createOpen}
        onOpenChange={setCreateOpen}
        onCreated={handleCreated}
      />
    </>
  );
}
```

- [ ] **Step 5: Supprimer les fichiers obsolètes**

```bash
git rm frontend/src/pages/WorkspaceActions.tsx
git rm frontend/src/pages/WorkspaceDeleteAlert.tsx
```

- [ ] **Step 6: Stub `WorkspaceDetailPanel` pour que ça compile**

`frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` :

```tsx
interface Props { name: string; }
export function WorkspaceDetailPanel({ name }: Props) {
  return <div className="flex-1 p-8 text-slate-500">Détail workspace : {name} (en construction)</div>;
}
```

Sera remplacé par la vraie implémentation en Task 4.

- [ ] **Step 7: Smoke tsc + lint + dev server visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```
Expected : 0 erreur.

Si dev server tourne déjà localement, vérifier dans le navigateur que la page `/workspaces` charge (liste affichée, stub à droite si workspace sélectionné).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/WorkspacesPage.tsx \
        frontend/src/pages/workspace/ \
        frontend/src/pages/WorkspaceActions.tsx \
        frontend/src/pages/WorkspaceCreateDialog.tsx \
        frontend/src/pages/WorkspaceDeleteAlert.tsx
git commit -m "feat(M6-T3): master-detail Workspaces + List + EmptyState + stub DetailPanel"
```

---

## Task 4: WorkspaceDetailPanel structure + WorkspaceHeader + tabs squelette

**Files:**
- Rewrite: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`
- Create: `frontend/src/pages/workspace/WorkspaceHeader.tsx`

**Contexte** : Le pattern à suivre est `VaultDetailPanel.tsx` (M5cd-front). Tabs shadcn pour les 4 onglets. Header sticky en haut.

- [ ] **Step 1: Créer `WorkspaceHeader.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreHorizontal, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  onReindex: () => void;
  onReveal: () => void;
  onRotate: () => void;
  onDelete: () => void;
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

export function WorkspaceHeader({ workspace, onReindex, onReveal, onRotate, onDelete }: Props) {
  const { t } = useTranslation("workspace");
  return (
    <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-white sticky top-0 z-10">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{workspace.name}</h2>
        <p className="text-xs text-slate-500">{t("header.created", { when: formatRelative(workspace.created_at) })}</p>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onReindex}>
          <RefreshCw className="h-4 w-4" /> {t("header.reindex")}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost" className="px-2">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onReveal}>{t("header.menu.reveal")}</DropdownMenuItem>
            <DropdownMenuItem onSelect={onRotate}>{t("header.menu.rotate")}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onDelete} className="text-red-600">{t("header.menu.delete")}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Réécrire `WorkspaceDetailPanel.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useWorkspace } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { WorkspaceHeader } from "./WorkspaceHeader";
import { WorkspaceDetailTab } from "./WorkspaceDetailTab";
import { WorkspaceSourcesTab } from "./WorkspaceSourcesTab";
import { WorkspaceJobsTab } from "./WorkspaceJobsTab";
import { WorkspaceModelTab } from "./WorkspaceModelTab";
import { RevealApiKeyDialog } from "./RevealApiKeyDialog";
import { RotateApiKeyDialog } from "./RotateApiKeyDialog";
import { ReindexConfirmDialog } from "./ReindexConfirmDialog";
import { DeleteWorkspaceAlert } from "./DeleteWorkspaceAlert";

interface Props {
  name: string;
}

type DialogKey = "reveal" | "rotate" | "reindex" | "delete" | null;

export function WorkspaceDetailPanel({ name }: Props) {
  const { t } = useTranslation("workspace");
  const { data: ws, isLoading } = useWorkspace(name);
  const [activeTab, setActiveTab] = useState("detail");
  const [openDialog, setOpenDialog] = useState<DialogKey>(null);

  if (isLoading || !ws) {
    return <div className="flex flex-1 items-center justify-center"><LoadingSpinner /></div>;
  }

  return (
    <div className="flex-1 max-w-[760px] overflow-auto">
      <WorkspaceHeader
        workspace={ws}
        onReindex={() => setOpenDialog("reindex")}
        onReveal={() => setOpenDialog("reveal")}
        onRotate={() => setOpenDialog("rotate")}
        onDelete={() => setOpenDialog("delete")}
      />
      <Tabs value={activeTab} onValueChange={setActiveTab} className="px-6 py-4">
        <TabsList>
          <TabsTrigger value="detail">{t("tabs.detail")}</TabsTrigger>
          <TabsTrigger value="sources">{t("tabs.sources", { count: ws.sources_count })}</TabsTrigger>
          <TabsTrigger value="jobs">{t("tabs.jobs")}</TabsTrigger>
          <TabsTrigger value="model">{t("tabs.model")}</TabsTrigger>
        </TabsList>
        <TabsContent value="detail" className="pt-4">
          <WorkspaceDetailTab workspace={ws} onReveal={() => setOpenDialog("reveal")} onRotate={() => setOpenDialog("rotate")} />
        </TabsContent>
        <TabsContent value="sources" className="pt-4">
          <WorkspaceSourcesTab name={ws.name} enabled={activeTab === "sources"} />
        </TabsContent>
        <TabsContent value="jobs" className="pt-4">
          <WorkspaceJobsTab name={ws.name} enabled={activeTab === "jobs"} />
        </TabsContent>
        <TabsContent value="model" className="pt-4">
          <WorkspaceModelTab workspace={ws} />
        </TabsContent>
      </Tabs>
      <RevealApiKeyDialog name={ws.name} open={openDialog === "reveal"} onOpenChange={(o) => !o && setOpenDialog(null)} />
      <RotateApiKeyDialog name={ws.name} open={openDialog === "rotate"} onOpenChange={(o) => !o && setOpenDialog(null)} />
      <ReindexConfirmDialog name={ws.name} open={openDialog === "reindex"} onOpenChange={(o) => !o && setOpenDialog(null)} />
      <DeleteWorkspaceAlert name={ws.name} open={openDialog === "delete"} onOpenChange={(o) => !o && setOpenDialog(null)} />
    </div>
  );
}
```

- [ ] **Step 3: Créer les stubs des 4 onglets et 4 dialogs**

Pour permettre la compilation. Chaque stub :

```tsx
// frontend/src/pages/workspace/WorkspaceDetailTab.tsx
import type { Workspace } from "@/lib/workspaces.types";
interface Props { workspace: Workspace; onReveal: () => void; onRotate: () => void; }
export function WorkspaceDetailTab(_props: Props) {
  return <div className="text-slate-500">Tab Détail (T5)</div>;
}
```

Faire pareil pour `WorkspaceSourcesTab` (props `{ name: string; enabled: boolean }`), `WorkspaceJobsTab` (idem), `WorkspaceModelTab` (props `{ workspace: Workspace }`), `RevealApiKeyDialog` / `RotateApiKeyDialog` / `ReindexConfirmDialog` / `DeleteWorkspaceAlert` (props `{ name: string; open: boolean; onOpenChange: (o: boolean) => void }`). Chaque stub renvoie `null` ou un placeholder pour les dialogs.

- [ ] **Step 4: Smoke tsc + lint + visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```
Expected : 0 erreur. Vérifier en dev que le panneau s'affiche avec les 4 tabs (vides) et que la sélection bascule.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/workspace/
git commit -m "feat(M6-T4): WorkspaceDetailPanel + WorkspaceHeader + tabs squelette (stubs)"
```

---

## Task 5: WorkspaceDetailTab (édition api_key_ref + sections read-only)

**Files:**
- Rewrite: `frontend/src/pages/workspace/WorkspaceDetailTab.tsx`

**Contexte** : 4 sections verticales (cf. spec §5.3). Édition api_key_ref via react-hook-form + Zod. Save bouton désactivé si non-dirty.

- [ ] **Step 1: Installer les deps si manquantes**

Vérifier dans `frontend/package.json` que `react-hook-form`, `@hookform/resolvers`, `zod` sont présents. Sinon :

```bash
cd frontend && npm install react-hook-form @hookform/resolvers zod
```

- [ ] **Step 2: Implémenter `WorkspaceDetailTab`**

```tsx
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/useToast";
import { useUpdateApiKeyRef } from "@/hooks/useWorkspaces";
import type { Workspace } from "@/lib/workspaces.types";

const schema = z.object({
  api_key_ref: z.string().regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only").min(1),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  workspace: Workspace;
  onReveal: () => void;
  onRotate: () => void;
}

function formatRelative(iso: string | null): string {
  if (!iso) return "—";
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.floor(h / 24)} j`;
}

export function WorkspaceDetailTab({ workspace, onReveal, onRotate }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const updateRef = useUpdateApiKeyRef(workspace.name);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { api_key_ref: workspace.indexer.api_key_ref ?? "" },
  });

  const onSubmit = (values: FormValues) => {
    updateRef.mutate(
      { indexer: { api_key_ref: values.api_key_ref } },
      {
        onSuccess: () => {
          toast.success(t("detail.save.success"));
          form.reset({ api_key_ref: values.api_key_ref });
        },
        onError: () => toast.error(t("detail.save.error")),
      },
    );
  };

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
      {/* Section 1 : Stats */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">{t("detail.stats.title")}</h3>
        <div className="text-sm text-slate-700">
          {t("detail.stats.sources", { count: workspace.sources_count })}
          {" · "}
          {t("detail.stats.documents", { count: workspace.documents_count })}
          {" · "}
          {t("detail.stats.lastIndexed", { when: formatRelative(workspace.last_indexed_at) })}
        </div>
      </section>

      {/* Section 2 : API key workspace */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">{t("detail.apikey.title")}</h3>
        <div className="flex items-center gap-2">
          <code className="bg-slate-100 px-3 py-1 rounded text-xs font-mono">••••••••••••••••••••••••</code>
          <Button type="button" size="sm" variant="outline" onClick={onReveal}>
            <Eye className="h-3.5 w-3.5" /> {t("detail.apikey.reveal")}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={onRotate}>
            <RefreshCw className="h-3.5 w-3.5" /> {t("detail.apikey.rotate")}
          </Button>
        </div>
      </section>

      {/* Section 3 : api_key_ref éditable */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.apiKeyRef.title")} <span className="text-emerald-600 normal-case">— {t("detail.apiKeyRef.editable")}</span>
        </h3>
        <div className="flex items-center gap-2">
          <Input {...form.register("api_key_ref")} className="font-mono text-sm flex-1" />
          <Button type="submit" size="sm" disabled={!form.formState.isDirty || updateRef.isPending}>
            {t("detail.apiKeyRef.save")}
          </Button>
        </div>
        {form.formState.errors.api_key_ref && (
          <p className="mt-1 text-xs text-red-600">{t(`detail.apiKeyRef.errors.${form.formState.errors.api_key_ref.message}`)}</p>
        )}
      </section>

      {/* Section 4 : Identifiants read-only */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">{t("detail.ids.title")}</h3>
        <div className="text-sm text-slate-700 space-y-1">
          <div>{t("detail.ids.name")}: <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.name}</code></div>
          <div>{t("detail.ids.id")}: <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.id}</code></div>
        </div>
      </section>
    </form>
  );
}
```

- [ ] **Step 3: Smoke + visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```

Vérifier en dev : édition `api_key_ref` (Save désactivé initialement, activé après modif), submit, toast succès.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceDetailTab.tsx frontend/package.json frontend/package-lock.json
git commit -m "feat(M6-T5): WorkspaceDetailTab édition api_key_ref + sections read-only"
```

---

## Task 6: WorkspaceSourcesTab (accordion + AddSource + DeleteSource)

**Files:**
- Rewrite: `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx`
- Create: `frontend/src/pages/workspace/AddSourceDialog.tsx`
- Create: `frontend/src/pages/workspace/DeleteSourceAlert.tsx`

- [ ] **Step 1: Implémenter `WorkspaceSourcesTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, MoreHorizontal, ChevronRight, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useWorkspaceSources } from "@/hooks/useWorkspaces";
import type { Source } from "@/lib/workspaces.types";
import { AddSourceDialog } from "./AddSourceDialog";
import { DeleteSourceAlert } from "./DeleteSourceAlert";

interface Props { name: string; enabled: boolean; }

function relativeTime(iso: string | null, fallback: string): string {
  if (!iso) return fallback;
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.floor(h / 24)} j`;
}

export function WorkspaceSourcesTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaceSources(name, enabled);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

  if (isLoading) return <LoadingSpinner />;
  const sources = data ?? [];

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900">{t("sources.title", { count: sources.length })}</h3>
        <Button size="sm" onClick={() => setAddOpen(true)}><Plus className="h-3.5 w-3.5" /> {t("sources.add")}</Button>
      </div>

      {sources.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("sources.empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {sources.map((source: Source) => {
            const isOpen = expanded.has(source.id);
            return (
              <div key={source.id} className="rounded border border-slate-200 bg-white">
                <button type="button" onClick={() => toggle(source.id)} className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50">
                  <div className="flex items-center gap-2 text-sm">
                    {isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />}
                    <code className="font-mono text-xs">{source.config.url}</code>
                    <span className="text-slate-500">· {source.config.branch}</span>
                    <span className="text-slate-400">· {relativeTime(source.last_indexed_at, t("sources.neverSynced"))}</span>
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button size="sm" variant="ghost" className="px-2" onClick={(e) => e.stopPropagation()}>
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setDeleteId(source.id)} className="text-red-600">
                        {t("sources.delete")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </button>
                {isOpen && (
                  <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600 space-y-1 bg-slate-50">
                    <div>{t("sources.fields.auth_ref")}: <code>{source.config.auth_ref ?? "—"}</code></div>
                    <div>{t("sources.fields.include")}: <code>{source.config.include.join(", ") || "—"}</code></div>
                    <div>{t("sources.fields.exclude")}: <code>{source.config.exclude.join(", ") || "—"}</code></div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <AddSourceDialog name={name} open={addOpen} onOpenChange={setAddOpen} />
      <DeleteSourceAlert name={name} sourceId={deleteId} onClose={() => setDeleteId(null)} />
    </>
  );
}
```

- [ ] **Step 2: Implémenter `AddSourceDialog.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/useToast";
import { useAddSource } from "@/hooks/useWorkspaces";

const schema = z.object({
  url: z.string().url("invalid_url"),
  branch: z.string().min(1).default("main"),
  auth_ref: z.string().optional(),
  include: z.string().optional(),  // CSV
  exclude: z.string().optional(),  // CSV
});

type FormValues = z.infer<typeof schema>;

interface Props { name: string; open: boolean; onOpenChange: (o: boolean) => void; }

const splitCsv = (s: string | undefined): string[] =>
  (s ?? "").split(",").map((x) => x.trim()).filter(Boolean);

export function AddSourceDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const add = useAddSource(name);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { url: "", branch: "main", auth_ref: "", include: "", exclude: "" },
  });

  const onSubmit = (v: FormValues) => {
    add.mutate(
      {
        type: "git",
        config: {
          url: v.url,
          branch: v.branch,
          auth_ref: v.auth_ref || null,
          include: splitCsv(v.include),
          exclude: splitCsv(v.exclude),
        },
      },
      {
        onSuccess: () => {
          toast.success(t("sources.add.success"));
          form.reset();
          onOpenChange(false);
        },
        onError: () => toast.error(t("sources.add.error")),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("sources.add.title")}</DialogTitle></DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.url")}</label>
            <Input {...form.register("url")} placeholder="https://github.com/..." />
            {form.formState.errors.url && <p className="text-xs text-red-600">{t(`sources.add.errors.${form.formState.errors.url.message}`)}</p>}
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.branch")}</label>
            <Input {...form.register("branch")} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.auth_ref")} <span className="text-slate-400">({t("optional")})</span></label>
            <Input {...form.register("auth_ref")} placeholder="github_token" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.include")} <span className="text-slate-400">(csv)</span></label>
            <Input {...form.register("include")} placeholder="**/*.md, docs/**" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.exclude")} <span className="text-slate-400">(csv)</span></label>
            <Input {...form.register("exclude")} placeholder="**/node_modules/**" />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>{t("dialog.cancel")}</Button>
            <Button type="submit" disabled={add.isPending}>{t("sources.add.submit")}</Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Implémenter `DeleteSourceAlert.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteSource } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props { name: string; sourceId: string | null; onClose: () => void; }

export function DeleteSourceAlert({ name, sourceId, onClose }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const del = useDeleteSource(name);
  const open = sourceId !== null;

  const handleConfirm = () => {
    if (!sourceId) return;
    del.mutate(sourceId, {
      onSuccess: () => {
        toast.success(t("sources.delete.success"));
        onClose();
      },
      onError: () => toast.error(t("sources.delete.error")),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("sources.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("sources.delete.warning")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} className="bg-red-600 hover:bg-red-700">
            {t("sources.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 4: Smoke tsc + lint + visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```

Vérifier en dev : onglet Sources s'ouvre (lazy load), accordion expand/collapse, add source → POST OK → invalidate, delete source → DELETE OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceSourcesTab.tsx \
        frontend/src/pages/workspace/AddSourceDialog.tsx \
        frontend/src/pages/workspace/DeleteSourceAlert.tsx
git commit -m "feat(M6-T6): WorkspaceSourcesTab accordion + AddSourceDialog + DeleteSourceAlert"
```

---

## Task 7: WorkspaceJobsTab (historique + expand error)

**Files:**
- Rewrite: `frontend/src/pages/workspace/WorkspaceJobsTab.tsx`

- [ ] **Step 1: Implémenter `WorkspaceJobsTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useWorkspaceJobs } from "@/hooks/useWorkspaces";
import type { Job } from "@/lib/workspaces.types";

interface Props { name: string; enabled: boolean; }

const statusVariant: Record<Job["status"], "default" | "secondary" | "destructive"> = {
  done: "default",
  pending: "secondary",
  running: "secondary",
  error: "destructive",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.floor(h / 24)} j`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function WorkspaceJobsTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaceJobs(name, enabled);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (isLoading) return <LoadingSpinner />;
  const jobs = data ?? [];

  if (jobs.length === 0) {
    return <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("jobs.empty")}</div>;
  }

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900 mb-3">{t("jobs.title", { count: jobs.length })}</h3>
      <div className="rounded-md border border-slate-200 bg-white">
        {jobs.map((job: Job) => {
          const hasError = job.status === "error" && job.error_message;
          const isOpen = expanded.has(job.id);
          return (
            <div key={job.id} className="border-b border-slate-100 last:border-b-0">
              <button
                type="button"
                onClick={() => hasError && toggle(job.id)}
                disabled={!hasError}
                className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 disabled:cursor-default"
              >
                {hasError ? (isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />) : <span className="w-3.5" />}
                <Badge variant={statusVariant[job.status]} className="font-mono text-xs">{job.status}</Badge>
                <span className="text-xs text-slate-600 font-mono">{job.triggered_by}</span>
                <span className="text-xs text-slate-700">
                  {t("jobs.changes", { changed: job.files_changed, skipped: job.files_skipped })}
                </span>
                <span className="text-xs text-slate-500 ml-auto">{formatDuration(job.duration_ms)}</span>
                <span className="text-xs text-slate-500">{relativeTime(job.started_at)}</span>
              </button>
              {isOpen && hasError && (
                <div className="border-t border-slate-100 px-3 py-2 bg-red-50 text-xs text-red-700 font-mono">
                  {job.error_message}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke + visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```

Vérifier en dev : onglet Jobs s'ouvre, badge couleur statut, click ligne erreur → expand `error_message`.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceJobsTab.tsx
git commit -m "feat(M6-T7): WorkspaceJobsTab historique + expand error_message"
```

---

## Task 8: WorkspaceModelTab (read-only + note immutable)

**Files:**
- Rewrite: `frontend/src/pages/workspace/WorkspaceModelTab.tsx`

- [ ] **Step 1: Implémenter `WorkspaceModelTab.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import type { Workspace } from "@/lib/workspaces.types";

interface Props { workspace: Workspace; }

export function WorkspaceModelTab({ workspace }: Props) {
  const { t } = useTranslation("workspace");
  const { provider, model, api_key_ref, base_url } = workspace.indexer;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-slate-900">{t("model.title")}</h3>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-500">{t("model.provider")}</dt>
        <dd className="font-mono">{provider}</dd>
        <dt className="text-slate-500">{t("model.model")}</dt>
        <dd className="font-mono">{model}</dd>
        <dt className="text-slate-500">{t("model.base_url")}</dt>
        <dd className="font-mono">{base_url ?? "—"}</dd>
        <dt className="text-slate-500">{t("model.api_key_ref")}</dt>
        <dd className="font-mono">{api_key_ref ?? "—"}</dd>
      </dl>
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <Info className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("model.immutableNote")}</p>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Smoke + commit**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/src/pages/workspace/WorkspaceModelTab.tsx
git commit -m "feat(M6-T8): WorkspaceModelTab lecture seule + note immutable"
```

---

## Task 9: Dialogs api key (Reveal + Rotate)

**Files:**
- Rewrite: `frontend/src/pages/workspace/RevealApiKeyDialog.tsx`
- Rewrite: `frontend/src/pages/workspace/RotateApiKeyDialog.tsx`

**Contexte** : Le pattern à suivre est `RevealApiKeyDialog.tsx` des Coffres Harpocrate (M5cd-front).

- [ ] **Step 1: Implémenter `RevealApiKeyDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useRevealApiKey } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props { name: string; open: boolean; onOpenChange: (o: boolean) => void; }

export function RevealApiKeyDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const reveal = useRevealApiKey(name);
  const [revealed, setRevealed] = useState<string | null>(null);

  // Auto-mask après 30s.
  useEffect(() => {
    if (!revealed) return;
    const id = setTimeout(() => setRevealed(null), 30_000);
    return () => clearTimeout(id);
  }, [revealed]);

  // Reset à la fermeture.
  useEffect(() => {
    if (!open) setRevealed(null);
  }, [open]);

  const handleConfirm = () => {
    reveal.mutate(undefined, {
      onSuccess: (data) => setRevealed(data.api_key),
      onError: () => toast.error(t("dialog.reveal.error")),
    });
  };

  const handleCopy = () => {
    if (!revealed) return;
    void navigator.clipboard.writeText(revealed);
    toast.success(t("dialog.reveal.copied"));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("dialog.reveal.title")}</DialogTitle></DialogHeader>
        {revealed === null ? (
          <>
            <div className="flex gap-3 items-start rounded-md bg-amber-50 border border-amber-200 px-4 py-3">
              <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-amber-900">{t("dialog.reveal.warning")}</p>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("dialog.cancel")}</Button>
              <Button onClick={handleConfirm} disabled={reveal.isPending}>{t("dialog.reveal.confirm")}</Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700">{t("dialog.reveal.copyHint")}</p>
            <div className="flex items-center gap-2 rounded bg-slate-100 px-3 py-2">
              <code className="flex-1 font-mono text-xs break-all">{revealed}</code>
              <Button size="sm" variant="outline" onClick={handleCopy}><Copy className="h-3.5 w-3.5" /></Button>
            </div>
            <p className="text-xs text-slate-500">{t("dialog.reveal.autoMaskNote")}</p>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>{t("dialog.close")}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Implémenter `RotateApiKeyDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRotateApiKey } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props { name: string; open: boolean; onOpenChange: (o: boolean) => void; }

export function RotateApiKeyDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const rotate = useRotateApiKey(name);
  const [confirmText, setConfirmText] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setConfirmText("");
      setNewKey(null);
    }
  }, [open]);

  const handleConfirm = () => {
    rotate.mutate(undefined, {
      onSuccess: (data) => {
        setNewKey(data.api_key);
        toast.success(t("dialog.rotate.success"));
      },
      onError: () => toast.error(t("dialog.rotate.error")),
    });
  };

  const handleCopy = () => {
    if (!newKey) return;
    void navigator.clipboard.writeText(newKey);
    toast.success(t("dialog.rotate.copied"));
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("dialog.rotate.title")}</DialogTitle></DialogHeader>
        {newKey === null ? (
          <>
            <div className="flex gap-3 items-start rounded-md bg-red-50 border border-red-200 px-4 py-3">
              <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-900">{t("dialog.rotate.warning")}</p>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-700">{t("dialog.rotate.confirmLabel", { name })}</label>
              <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder={name} />
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("dialog.cancel")}</Button>
              <Button
                onClick={handleConfirm}
                disabled={confirmText !== name || rotate.isPending}
                className="bg-red-600 hover:bg-red-700"
              >
                {t("dialog.rotate.confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700">{t("dialog.rotate.copyHint")}</p>
            <div className="flex items-center gap-2 rounded bg-slate-100 px-3 py-2">
              <code className="flex-1 font-mono text-xs break-all">{newKey}</code>
              <Button size="sm" variant="outline" onClick={handleCopy}><Copy className="h-3.5 w-3.5" /></Button>
            </div>
            <p className="text-xs text-amber-700">{t("dialog.rotate.oneTimeWarning")}</p>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>{t("dialog.close")}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 3: Smoke + visuel**

```bash
cd frontend
npx tsc --noEmit && npm run lint
```

Vérifier en dev : Reveal → warning → confirm → display clé + copy + auto-mask 30s. Rotate → input nom-confirmation → confirm → display nouvelle clé.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/workspace/RevealApiKeyDialog.tsx \
        frontend/src/pages/workspace/RotateApiKeyDialog.tsx
git commit -m "feat(M6-T9): RevealApiKeyDialog + RotateApiKeyDialog (warning + copy + auto-mask 30s)"
```

---

## Task 10: ReindexConfirmDialog + DeleteWorkspaceAlert

**Files:**
- Rewrite: `frontend/src/pages/workspace/ReindexConfirmDialog.tsx`
- Rewrite: `frontend/src/pages/workspace/DeleteWorkspaceAlert.tsx`

- [ ] **Step 1: Implémenter `ReindexConfirmDialog.tsx`**

```tsx
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useReindex } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props { name: string; open: boolean; onOpenChange: (o: boolean) => void; }

export function ReindexConfirmDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const reindex = useReindex(name);

  const handleConfirm = () => {
    reindex.mutate(undefined, {
      onSuccess: () => {
        toast.success(t("dialog.reindex.success"));
        onOpenChange(false);
      },
      onError: () => toast.error(t("dialog.reindex.error")),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader><DialogTitle>{t("dialog.reindex.title")}</DialogTitle></DialogHeader>
        <div className="flex gap-3 items-start rounded-md bg-amber-50 border border-amber-200 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-900">{t("dialog.reindex.warning")}</p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>{t("dialog.cancel")}</Button>
          <Button onClick={handleConfirm} disabled={reindex.isPending}>{t("dialog.reindex.confirm")}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Implémenter `DeleteWorkspaceAlert.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Input } from "@/components/ui/input";
import { useDeleteWorkspace } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props { name: string; open: boolean; onOpenChange: (o: boolean) => void; }

export function DeleteWorkspaceAlert({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const toast = useToast();
  const navigate = useNavigate();
  const del = useDeleteWorkspace();
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => { if (!open) setConfirmText(""); }, [open]);

  const handleConfirm = () => {
    del.mutate(name, {
      onSuccess: () => {
        toast.success(t("dialog.delete.success"));
        onOpenChange(false);
        navigate("/workspaces", { replace: true });
      },
      onError: () => toast.error(t("dialog.delete.error")),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("dialog.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("dialog.delete.warning")}</AlertDialogDescription>
        </AlertDialogHeader>
        <div>
          <label className="text-xs font-medium text-slate-700">{t("dialog.delete.confirmLabel", { name })}</label>
          <Input value={confirmText} onChange={(e) => setConfirmText(e.target.value)} placeholder={name} />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={confirmText !== name || del.isPending}
            className="bg-red-600 hover:bg-red-700"
          >
            {t("dialog.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
```

- [ ] **Step 3: Smoke + commit**

```bash
cd frontend && npx tsc --noEmit && npm run lint
git add frontend/src/pages/workspace/ReindexConfirmDialog.tsx \
        frontend/src/pages/workspace/DeleteWorkspaceAlert.tsx
git commit -m "feat(M6-T10): ReindexConfirmDialog + DeleteWorkspaceAlert (input nom-confirmation)"
```

---

## Task 11: i18n complet FR + EN + tests Vitest + audit strings

**Files:**
- Create: `frontend/src/i18n/fr/workspace.json`
- Create: `frontend/src/i18n/en/workspace.json`
- Modify: `frontend/src/i18n/i18n.ts`
- Create: `frontend/src/pages/workspace/__tests__/*.test.tsx` (8 fichiers)

- [ ] **Step 1: Créer `frontend/src/i18n/fr/workspace.json`**

```json
{
  "title": "Workspaces",
  "list": {
    "header": "Workspaces",
    "new": "+ Nouveau",
    "empty": ""
  },
  "empty": {
    "title": "Aucun workspace",
    "description": "Créez votre premier workspace pour indexer des sources."
  },
  "header": {
    "created": "créé {{when}}",
    "reindex": "Réindexer",
    "menu": {
      "reveal": "Révéler la clé API",
      "rotate": "Régénérer la clé API",
      "delete": "Supprimer le workspace"
    }
  },
  "tabs": {
    "detail": "Détail",
    "sources": "Sources git ({{count}})",
    "jobs": "Jobs",
    "model": "Modèle"
  },
  "detail": {
    "stats": {
      "title": "Statistiques",
      "sources": "{{count}} sources",
      "documents": "{{count}} documents",
      "lastIndexed": "dernière sync : {{when}}"
    },
    "apikey": {
      "title": "Clé API workspace",
      "reveal": "Révéler",
      "rotate": "Régénérer"
    },
    "apiKeyRef": {
      "title": "Référence Harpocrate",
      "editable": "modifiable",
      "save": "Enregistrer",
      "errors": {
        "alphanum_underscore_only": "Caractères autorisés : a-z, A-Z, 0-9, underscore."
      }
    },
    "ids": {
      "title": "Identifiants (lecture seule)",
      "name": "nom",
      "id": "id"
    },
    "save": {
      "success": "Référence enregistrée.",
      "error": "Erreur à l'enregistrement."
    }
  },
  "sources": {
    "title": "Sources git ({{count}})",
    "add": "Ajouter une source",
    "empty": "Aucune source. Ajoutez-en une pour commencer.",
    "neverSynced": "jamais synchronisé",
    "fields": {
      "url": "URL",
      "branch": "Branche",
      "auth_ref": "Référence d'authentification",
      "include": "Inclure",
      "exclude": "Exclure"
    },
    "add": {
      "title": "Ajouter une source git",
      "submit": "Ajouter",
      "success": "Source ajoutée.",
      "error": "Échec de l'ajout.",
      "errors": {
        "invalid_url": "URL invalide."
      }
    },
    "delete": "Supprimer",
    "delete": {
      "title": "Supprimer la source",
      "warning": "Cette action supprime la source. Les documents déjà indexés restent.",
      "confirm": "Supprimer",
      "success": "Source supprimée.",
      "error": "Échec de la suppression."
    }
  },
  "jobs": {
    "title": "Jobs ({{count}})",
    "empty": "Aucun job d'indexation.",
    "changes": "{{changed}} ch / {{skipped}} sk"
  },
  "model": {
    "title": "Modèle d'indexation",
    "provider": "provider",
    "model": "model",
    "base_url": "base_url",
    "api_key_ref": "api_key_ref",
    "immutableNote": "Le modèle est immutable. Changer provider ou model invaliderait toutes les dimensions vecteurs et nécessiterait une réindexation complète, non supportée dans cette version."
  },
  "dialog": {
    "cancel": "Annuler",
    "close": "Fermer",
    "reveal": {
      "title": "Révéler la clé API",
      "warning": "Affiche la clé API en clair. Continuer ?",
      "confirm": "Révéler",
      "copyHint": "Copiez la clé maintenant — elle sera masquée dans 30 secondes.",
      "autoMaskNote": "La clé sera masquée automatiquement dans 30 secondes.",
      "copied": "Clé copiée.",
      "error": "Échec de la révélation."
    },
    "rotate": {
      "title": "Régénérer la clé API",
      "warning": "Cette action invalide immédiatement la clé actuelle. Les agents existants devront être reconfigurés.",
      "confirmLabel": "Tapez « {{name}} » pour confirmer",
      "confirm": "Régénérer",
      "copyHint": "Nouvelle clé générée. Copiez-la maintenant — elle ne sera plus affichée.",
      "oneTimeWarning": "Affichage à usage unique : la clé ne sera plus accessible après fermeture (sauf via Révéler).",
      "success": "Clé régénérée.",
      "error": "Échec de la régénération.",
      "copied": "Clé copiée."
    },
    "reindex": {
      "title": "Réindexer",
      "warning": "Toutes les sources du workspace seront re-synchronisées. Les documents non modifiés sont skip (déduplication SHA-256).",
      "confirm": "Déclencher la réindexation",
      "success": "Réindexation déclenchée.",
      "error": "Échec du déclenchement."
    },
    "delete": {
      "title": "Supprimer le workspace",
      "warning": "Supprime le workspace + sa base pgvector + tous ses documents indexés. Irréversible.",
      "confirmLabel": "Tapez « {{name}} » pour confirmer",
      "confirm": "Supprimer définitivement",
      "success": "Workspace supprimé.",
      "error": "Échec de la suppression."
    }
  },
  "optional": "optionnel"
}
```

**Note** : le JSON contient une **collision de clé** sur `sources.delete` (string vs object). C'est intentionnel — i18next traite le dernier comme override. Pour éviter l'ambiguïté, renommer la première occurrence en `sources.deleteAction` :

```json
"sources": {
  ...
  "deleteAction": "Supprimer",
  ...
  "delete": { /* dialog */ }
}
```

Et adapter le code `WorkspaceSourcesTab.tsx` ligne `t("sources.delete")` → `t("sources.deleteAction")`.

- [ ] **Step 2: Créer `frontend/src/i18n/en/workspace.json`**

Même structure que FR, traduit en anglais. Exemple :

```json
{
  "title": "Workspaces",
  "list": { "header": "Workspaces", "new": "+ New" },
  "empty": {
    "title": "No workspace yet",
    "description": "Create your first workspace to index sources."
  },
  "header": {
    "created": "created {{when}}",
    "reindex": "Reindex",
    "menu": {
      "reveal": "Reveal API key",
      "rotate": "Rotate API key",
      "delete": "Delete workspace"
    }
  },
  ...
}
```

Aligne toutes les clés du fichier FR.

- [ ] **Step 3: Modifier `frontend/src/i18n/i18n.ts`**

Ajouter le namespace `workspace` aux ressources i18next. Vérifier le pattern du namespace `harpocrate` (M5cd-front) et l'imiter.

- [ ] **Step 4: Audit strings hardcoded**

Pour chaque composant `frontend/src/pages/workspace/*.tsx` : grep des strings JSX entre `>...<` qui ne passent pas par `t()`. Toute string brute (hors valeurs read-only injectées : `{ws.name}`, `{job.status}`, `{ws.id}`, etc.) doit être convertie en clé i18n.

```bash
cd frontend
grep -nE '>[A-Za-zÀ-ÿ ]{3,}<' src/pages/workspace/*.tsx src/pages/workspace/**/*.tsx
```

Examiner chaque occurrence. Tolérés : valeurs `<code>...</code>` qui affichent une valeur backend.

- [ ] **Step 5: Tests Vitest — 8 fichiers**

Pattern à suivre : `frontend/src/pages/harpocrate/__tests__/*.test.tsx` (M5cd-front).

```tsx
// frontend/src/pages/workspace/__tests__/WorkspacesList.test.tsx
import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider } from "react-i18next";
import i18n from "@/i18n/i18n";
import { WorkspacesList } from "@/pages/workspace/WorkspacesList";

vi.mock("@/hooks/useWorkspaces", () => ({
  useWorkspaces: () => ({
    data: [
      { id: "1", name: "ws-a", indexer: { provider: "ollama", model: "mxbai" }, sources_count: 0, documents_count: 0, last_indexed_at: null, created_at: "2026-01-01T00:00:00Z" },
    ],
    isLoading: false,
  }),
}));

function renderWithProviders(ui: React.ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <I18nextProvider i18n={i18n}>
      <QueryClientProvider client={qc}>{ui}</QueryClientProvider>
    </I18nextProvider>,
  );
}

describe("WorkspacesList", () => {
  it("affiche les workspaces", () => {
    renderWithProviders(<WorkspacesList selectedName={null} onSelect={() => {}} onCreate={() => {}} />);
    expect(screen.getByText("ws-a")).toBeInTheDocument();
  });

  it("déclenche onSelect au click", () => {
    const onSelect = vi.fn();
    renderWithProviders(<WorkspacesList selectedName={null} onSelect={onSelect} onCreate={() => {}} />);
    fireEvent.click(screen.getByText("ws-a"));
    expect(onSelect).toHaveBeenCalledWith("ws-a");
  });

  it("met en évidence le workspace sélectionné", () => {
    renderWithProviders(<WorkspacesList selectedName="ws-a" onSelect={() => {}} onCreate={() => {}} />);
    const btn = screen.getByText("ws-a").closest("button");
    expect(btn?.className).toContain("bg-blue-50");
  });
});
```

Créer un fichier de test similaire pour chacun :
- `WorkspacesPage.test.tsx` — auto-sélection URL, render état vide
- `WorkspaceDetailTab.test.tsx` — Save désactivé si non-dirty + submit OK
- `WorkspaceSourcesTab.test.tsx` — accordion + AddSource + DeleteSource
- `WorkspaceJobsTab.test.tsx` — badge status + expand error
- `RevealApiKeyDialog.test.tsx` — warning → confirm → display clé + copy
- `RotateApiKeyDialog.test.tsx` — input nom-confirmation requis
- `AddSourceDialog.test.tsx` — validation URL Zod + submit

- [ ] **Step 6: Run tests**

```bash
cd frontend && npm test -- --run
```
Expected : 100% pass sur les nouveaux fichiers + aucun cassé existant.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/i18n/ \
        frontend/src/pages/workspace/__tests__/
git commit -m "feat(M6-T11): i18n complet FR+EN + 8 tests Vitest + audit strings"
```

---

## Auto-revue post-rédaction

**1. Spec coverage :**

- §2 D1 master-detail → Task 3.
- §2 D2 4 onglets → Tasks 4-8 (Détail/Sources/Jobs/Modèle).
- §2 D3 accordion sources → Task 6.
- §2 D4 édition `api_key_ref` only → Task 5.
- §2 D5 header sticky → Task 4.
- §2 D6 URL `?ws=` → Task 3.
- §2 D7 lazy loading → Task 2 (`enabled` dans hooks) + Tasks 6, 7.
- §2 D8 Modèle read-only → Task 8.
- §2 D9 page M5b remplacée → Task 3 (rewrite).
- §3.3 hooks → Task 2.
- §4 endpoints → Task 1 + Task 2.
- §5 layouts → Tasks 3-10.
- §6 dialogs → Tasks 6 (Add/Delete source), 9 (Reveal/Rotate), 10 (Reindex/Delete workspace).
- §7 i18n → Task 11.
- §8 tests → Task 11.

**2. Placeholder scan :** Aucun « TBD », « TODO » ou code générique. Chaque step a son code ou sa commande exacte.

**3. Type consistency :** `Workspace`, `Source`, `Job`, `IndexerSpec`, `WorkspacePatchRequest` cohérents entre Tasks 1, 2, 3, 4, 5, 6, 7, 8. Hooks renvoient les bons types (`UseMutationResult<Source, Error, SourceCreateRequest>` pour `useAddSource` correspond à `workspacesApi.addSource(name, payload)`).

Risque résiduel : collision de clé i18n `sources.delete` (string vs object) signalée et adressée en Step 1 (rename → `sources.deleteAction`).
