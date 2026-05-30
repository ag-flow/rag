# Enrichissement LLM — Frontend (Jalon 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Page globale de gestion des prompt templates (sidebar) + onglet Triggers dans chaque workspace pour configurer les déclencheurs par extension de fichier.

**Architecture:** Nouveaux fichiers types/API/hooks dans `lib/` et `hooks/`, deux namespaces i18n (`prompts` et `triggers`), page `/prompts` dans la sidebar, onglet `triggers` dans `WorkspaceDetailPanel`.

**Tech Stack:** React 18 / TypeScript strict / TanStack Query / shadcn/ui / i18next / react-router-dom

---

## Structure des fichiers

### Frontend (créer)
- `frontend/src/lib/enrichments.types.ts`
- `frontend/src/lib/enrichments.ts`
- `frontend/src/hooks/useEnrichments.ts`
- `frontend/src/i18n/fr/prompts.json`
- `frontend/src/i18n/en/prompts.json`
- `frontend/src/i18n/fr/triggers.json`
- `frontend/src/i18n/en/triggers.json`
- `frontend/src/pages/PromptsPage.tsx`
- `frontend/src/pages/workspace/AddPromptDialog.tsx`
- `frontend/src/pages/workspace/WorkspaceTriggersTab.tsx`
- `frontend/src/pages/workspace/AddTriggerDialog.tsx`

### Frontend (modifier)
- `frontend/src/routes.tsx` — route `/prompts`
- `frontend/src/components/Sidebar.tsx` — entrée Prompts
- `frontend/src/lib/i18n.ts` — namespaces prompts + triggers
- `frontend/src/i18n/fr/nav.json` + `en/nav.json` — clé `items.prompts`
- `frontend/src/i18n/fr/workspace.json` + `en/workspace.json` — clé `tabs.triggers`
- `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` — onglet Triggers

---

## Task 1 : Types + API client + hooks + i18n

**Files:**
- Create: `frontend/src/lib/enrichments.types.ts`
- Create: `frontend/src/lib/enrichments.ts`
- Create: `frontend/src/hooks/useEnrichments.ts`
- Create: `frontend/src/i18n/fr/prompts.json`
- Create: `frontend/src/i18n/en/prompts.json`
- Create: `frontend/src/i18n/fr/triggers.json`
- Create: `frontend/src/i18n/en/triggers.json`
- Modify: `frontend/src/lib/i18n.ts`
- Modify: `frontend/src/i18n/fr/nav.json`
- Modify: `frontend/src/i18n/en/nav.json`
- Modify: `frontend/src/i18n/fr/workspace.json`
- Modify: `frontend/src/i18n/en/workspace.json`

- [ ] **Créer `frontend/src/lib/enrichments.types.ts`**

```typescript
export type PromptTemplate = {
  id: string;
  name: string;
  language: string;
  description: string | null;
  metadata_key: string;
  result_type: "text" | "json";
  result_schema: object | null;
  prompt: string;
  created_at: string;
  updated_at: string;
};

export type PromptTemplateCreate = {
  name: string;
  language: string;
  description?: string | null;
  metadata_key: string;
  result_type: "text" | "json";
  result_schema?: object | null;
  prompt: string;
};

export type PromptTemplatePatch = {
  description?: string | null;
  prompt?: string;
  result_schema?: object | null;
};

export type Trigger = {
  id: string;
  extension: string;
  enabled: boolean;
  created_at: string;
};

export type TriggerCreate = {
  extension: string;
  enabled?: boolean;
};

export type TriggerPatch = {
  enabled: boolean;
};

export type TriggerPrompt = {
  id: string;
  template_id: string;
  template_name: string;
  llm_id: string;
  llm_provider: string;
  llm_model: string;
  order_index: number;
  enabled: boolean;
};

export type TriggerPromptCreate = {
  template_id: string;
  llm_id: string;
  order_index: number;
  enabled?: boolean;
};
```

- [ ] **Créer `frontend/src/lib/enrichments.ts`**

```typescript
import { api } from "@/lib/api";
import type {
  PromptTemplate,
  PromptTemplateCreate,
  PromptTemplatePatch,
  Trigger,
  TriggerCreate,
  TriggerPatch,
  TriggerPrompt,
  TriggerPromptCreate,
} from "@/lib/enrichments.types";

export const enrichmentsApi = {
  // ── Prompt templates (global) ──
  listPrompts: () => api.get<PromptTemplate[]>("/api/admin/prompts"),

  createPrompt: (payload: PromptTemplateCreate) =>
    api.post<PromptTemplate>("/api/admin/prompts", payload),

  patchPrompt: (id: string, payload: PromptTemplatePatch) =>
    api.patch<PromptTemplate>(`/api/admin/prompts/${id}`, payload),

  deletePrompt: (id: string) => api.delete<void>(`/api/admin/prompts/${id}`),

  // ── Triggers par workspace ──
  listTriggers: (workspaceName: string) =>
    api.get<Trigger[]>(`/api/admin/workspaces/${workspaceName}/triggers`),

  createTrigger: (workspaceName: string, payload: TriggerCreate) =>
    api.post<Trigger>(`/api/admin/workspaces/${workspaceName}/triggers`, payload),

  patchTrigger: (workspaceName: string, triggerId: string, payload: TriggerPatch) =>
    api.patch<Trigger>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}`,
      payload,
    ),

  deleteTrigger: (workspaceName: string, triggerId: string) =>
    api.delete<void>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}`,
    ),

  // ── Trigger prompts ──
  listTriggerPrompts: (workspaceName: string, triggerId: string) =>
    api.get<TriggerPrompt[]>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts`,
    ),

  createTriggerPrompt: (
    workspaceName: string,
    triggerId: string,
    payload: TriggerPromptCreate,
  ) =>
    api.post<TriggerPrompt>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts`,
      payload,
    ),

  deleteTriggerPrompt: (
    workspaceName: string,
    triggerId: string,
    promptId: string,
  ) =>
    api.delete<void>(
      `/api/admin/workspaces/${workspaceName}/triggers/${triggerId}/prompts/${promptId}`,
    ),
};
```

- [ ] **Créer `frontend/src/hooks/useEnrichments.ts`**

```typescript
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { enrichmentsApi } from "@/lib/enrichments";
import type {
  PromptTemplateCreate,
  PromptTemplatePatch,
  TriggerCreate,
  TriggerPatch,
  TriggerPromptCreate,
} from "@/lib/enrichments.types";

const PROMPTS_KEY = ["prompts"] as const;
const triggersKey = (ws: string) => ["triggers", ws] as const;
const triggerPromptsKey = (ws: string, tid: string) =>
  ["trigger-prompts", ws, tid] as const;

// ── Prompts ──

export function usePrompts() {
  return useQuery({
    queryKey: PROMPTS_KEY,
    queryFn: enrichmentsApi.listPrompts,
    staleTime: 30_000,
  });
}

export function useCreatePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: PromptTemplateCreate) =>
      enrichmentsApi.createPrompt(payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

export function usePatchPrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, payload }: { id: string; payload: PromptTemplatePatch }) =>
      enrichmentsApi.patchPrompt(id, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

export function useDeletePrompt() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => enrichmentsApi.deletePrompt(id),
    onSuccess: () => void qc.invalidateQueries({ queryKey: PROMPTS_KEY }),
  });
}

// ── Triggers ──

export function useTriggers(workspaceName: string) {
  return useQuery({
    queryKey: triggersKey(workspaceName),
    queryFn: () => enrichmentsApi.listTriggers(workspaceName),
    staleTime: 30_000,
  });
}

export function useCreateTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerCreate) =>
      enrichmentsApi.createTrigger(workspaceName, payload),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

export function usePatchTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ triggerId, payload }: { triggerId: string; payload: TriggerPatch }) =>
      enrichmentsApi.patchTrigger(workspaceName, triggerId, payload),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

export function useDeleteTrigger(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (triggerId: string) =>
      enrichmentsApi.deleteTrigger(workspaceName, triggerId),
    onSuccess: () =>
      void qc.invalidateQueries({ queryKey: triggersKey(workspaceName) }),
  });
}

// ── Trigger prompts ──

export function useTriggerPrompts(workspaceName: string, triggerId: string) {
  return useQuery({
    queryKey: triggerPromptsKey(workspaceName, triggerId),
    queryFn: () => enrichmentsApi.listTriggerPrompts(workspaceName, triggerId),
    enabled: !!triggerId,
    staleTime: 30_000,
  });
}

export function useCreateTriggerPrompt(workspaceName: string, triggerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: TriggerPromptCreate) =>
      enrichmentsApi.createTriggerPrompt(workspaceName, triggerId, payload),
    onSuccess: () =>
      void qc.invalidateQueries({
        queryKey: triggerPromptsKey(workspaceName, triggerId),
      }),
  });
}

export function useDeleteTriggerPrompt(workspaceName: string, triggerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (promptId: string) =>
      enrichmentsApi.deleteTriggerPrompt(workspaceName, triggerId, promptId),
    onSuccess: () =>
      void qc.invalidateQueries({
        queryKey: triggerPromptsKey(workspaceName, triggerId),
      }),
  });
}
```

- [ ] **Créer `frontend/src/i18n/fr/prompts.json`**

```json
{
  "page_title": "Bibliothèque de prompts",
  "add_btn": "Nouveau prompt",
  "empty": "Aucun prompt configuré.",
  "col_name": "Nom",
  "col_language": "Langage",
  "col_metadata_key": "Clé résultat",
  "col_result_type": "Type",
  "col_description": "Description",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer ce prompt ?",
  "delete_confirm_body": "Le prompt sera supprimé définitivement. Erreur si référencé par un trigger.",
  "deleted_toast": "Prompt supprimé.",
  "error_referenced": "Ce prompt est utilisé par un trigger et ne peut pas être supprimé.",
  "add_dialog_title": "Nouveau prompt template",
  "field_name": "Nom (slug)",
  "field_language": "Langage",
  "field_language_placeholder": "csharp, python, typescript…",
  "field_metadata_key": "Clé de métadonnée",
  "field_metadata_key_placeholder": "documentation, public_functions…",
  "field_result_type": "Type de résultat",
  "field_result_type_text": "Texte libre",
  "field_result_type_json": "JSON structuré",
  "field_prompt": "Prompt (utilise {content})",
  "field_description": "Description (optionnel)",
  "save": "Créer",
  "cancel": "Annuler",
  "error_toast": "Erreur lors de la création.",
  "error_duplicate": "Un prompt avec ce nom existe déjà."
}
```

- [ ] **Créer `frontend/src/i18n/en/prompts.json`**

```json
{
  "page_title": "Prompt library",
  "add_btn": "New prompt",
  "empty": "No prompts configured.",
  "col_name": "Name",
  "col_language": "Language",
  "col_metadata_key": "Result key",
  "col_result_type": "Type",
  "col_description": "Description",
  "delete_btn": "Delete",
  "delete_confirm_title": "Delete this prompt?",
  "delete_confirm_body": "The prompt will be permanently deleted. Error if referenced by a trigger.",
  "deleted_toast": "Prompt deleted.",
  "error_referenced": "This prompt is used by a trigger and cannot be deleted.",
  "add_dialog_title": "New prompt template",
  "field_name": "Name (slug)",
  "field_language": "Language",
  "field_language_placeholder": "csharp, python, typescript…",
  "field_metadata_key": "Metadata key",
  "field_metadata_key_placeholder": "documentation, public_functions…",
  "field_result_type": "Result type",
  "field_result_type_text": "Free text",
  "field_result_type_json": "Structured JSON",
  "field_prompt": "Prompt (use {content})",
  "field_description": "Description (optional)",
  "save": "Create",
  "cancel": "Cancel",
  "error_toast": "Creation error.",
  "error_duplicate": "A prompt with this name already exists."
}
```

- [ ] **Créer `frontend/src/i18n/fr/triggers.json`**

```json
{
  "tab": "Triggers",
  "empty": "Aucun trigger configuré pour ce workspace.",
  "add_btn": "Ajouter un trigger",
  "col_extension": "Extension",
  "col_prompts": "Prompts",
  "col_enabled": "Activé",
  "delete_btn": "Supprimer",
  "delete_confirm_title": "Supprimer ce trigger ?",
  "delete_confirm_body": "Tous les prompts associés seront supprimés.",
  "deleted_toast": "Trigger supprimé.",
  "add_dialog_title": "Nouveau trigger",
  "field_extension": "Extension de fichier",
  "field_extension_placeholder": ".cs, .py, .ts…",
  "field_extension_help": "Avec le point, en minuscules",
  "save": "Créer",
  "cancel": "Annuler",
  "error_toast": "Erreur lors de la création.",
  "error_duplicate": "Un trigger pour cette extension existe déjà.",
  "prompts_title": "Prompts du trigger",
  "prompts_empty": "Aucun prompt — ajoutez-en un ci-dessous.",
  "add_prompt_btn": "Ajouter un prompt",
  "add_prompt_dialog_title": "Ajouter un prompt au trigger",
  "field_template": "Template de prompt",
  "field_llm": "LLM à utiliser",
  "field_order": "Ordre d'exécution",
  "prompt_add_save": "Ajouter",
  "prompt_delete_btn": "Retirer"
}
```

- [ ] **Créer `frontend/src/i18n/en/triggers.json`**

```json
{
  "tab": "Triggers",
  "empty": "No triggers configured for this workspace.",
  "add_btn": "Add trigger",
  "col_extension": "Extension",
  "col_prompts": "Prompts",
  "col_enabled": "Enabled",
  "delete_btn": "Delete",
  "delete_confirm_title": "Delete this trigger?",
  "delete_confirm_body": "All associated prompts will be deleted.",
  "deleted_toast": "Trigger deleted.",
  "add_dialog_title": "New trigger",
  "field_extension": "File extension",
  "field_extension_placeholder": ".cs, .py, .ts…",
  "field_extension_help": "With dot, lowercase",
  "save": "Create",
  "cancel": "Cancel",
  "error_toast": "Creation error.",
  "error_duplicate": "A trigger for this extension already exists.",
  "prompts_title": "Trigger prompts",
  "prompts_empty": "No prompts — add one below.",
  "add_prompt_btn": "Add prompt",
  "add_prompt_dialog_title": "Add prompt to trigger",
  "field_template": "Prompt template",
  "field_llm": "LLM to use",
  "field_order": "Execution order",
  "prompt_add_save": "Add",
  "prompt_delete_btn": "Remove"
}
```

- [ ] **Ajouter les namespaces dans `frontend/src/lib/i18n.ts`**

Lis le fichier i18n. Ajouter les imports et l'enregistrement de `prompts` et `triggers` (fr + en), en suivant le même pattern que les autres namespaces déjà enregistrés.

- [ ] **Ajouter `items.prompts` dans les fichiers nav**

Dans `frontend/src/i18n/fr/nav.json`, dans `items`, ajouter :
```json
"prompts": "Prompts"
```

Dans `frontend/src/i18n/en/nav.json` :
```json
"prompts": "Prompts"
```

- [ ] **Ajouter `tabs.triggers` dans les fichiers workspace**

Dans `frontend/src/i18n/fr/workspace.json`, dans `tabs`, ajouter :
```json
"triggers": "Triggers"
```

Dans `frontend/src/i18n/en/workspace.json` :
```json
"triggers": "Triggers"
```

- [ ] **Vérifier TypeScript + JSON**

```bash
cd frontend && npx tsc --noEmit
node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/prompts.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/fr/triggers.json','utf8')); console.log('OK')"
```

- [ ] **Commit**

```bash
git add frontend/src/lib/enrichments.types.ts \
        frontend/src/lib/enrichments.ts \
        frontend/src/hooks/useEnrichments.ts \
        frontend/src/i18n/fr/prompts.json \
        frontend/src/i18n/en/prompts.json \
        frontend/src/i18n/fr/triggers.json \
        frontend/src/i18n/en/triggers.json \
        frontend/src/lib/i18n.ts \
        frontend/src/i18n/fr/nav.json \
        frontend/src/i18n/en/nav.json \
        frontend/src/i18n/fr/workspace.json \
        frontend/src/i18n/en/workspace.json
git commit -m "feat(front): enrichments types + API + hooks + i18n prompts+triggers"
```

---

## Task 2 : PromptsPage + AddPromptDialog + route + sidebar

**Files:**
- Create: `frontend/src/pages/PromptsPage.tsx`
- Create: `frontend/src/pages/workspace/AddPromptDialog.tsx`
- Modify: `frontend/src/routes.tsx`
- Modify: `frontend/src/components/Sidebar.tsx`

- [ ] **Créer `frontend/src/pages/workspace/AddPromptDialog.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreatePrompt } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddPromptDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("prompts");
  const { toast } = useToast();
  const mutation = useCreatePrompt();

  const [name, setName] = useState("");
  const [language, setLanguage] = useState("");
  const [metadataKey, setMetadataKey] = useState("");
  const [resultType, setResultType] = useState<"text" | "json">("text");
  const [prompt, setPrompt] = useState("");
  const [description, setDescription] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setLanguage(""); setMetadataKey("");
      setResultType("text"); setPrompt(""); setDescription("");
    }
  }

  const canSubmit =
    name.trim().length > 0 &&
    language.trim().length > 0 &&
    metadataKey.trim().length > 0 &&
    prompt.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({
        name: name.trim(),
        language: language.trim(),
        metadata_key: metadataKey.trim(),
        result_type: resultType,
        prompt: prompt.trim(),
        description: description.trim() || null,
      });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="generate-doc-csharp"
                className="mt-1 font-mono"
              />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_language")}
              </Label>
              <Input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder={t("field_language_placeholder")}
                className="mt-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_metadata_key")}
              </Label>
              <Input
                value={metadataKey}
                onChange={(e) => setMetadataKey(e.target.value)}
                placeholder={t("field_metadata_key_placeholder")}
                className="mt-1 font-mono"
              />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_result_type")}
              </Label>
              <div className="flex gap-4 mt-2">
                {(["text", "json"] as const).map((rt) => (
                  <label key={rt} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      value={rt}
                      checked={resultType === rt}
                      onChange={() => setResultType(rt)}
                    />
                    {t(`field_result_type_${rt}`)}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_prompt")}
            </Label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Tu es un expert {language}. Génère la documentation de :\n\n{content}"
              className="mt-1 font-mono text-xs min-h-[120px]"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_description")}
            </Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Génère la documentation technique"
              className="mt-1"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Créer `frontend/src/pages/PromptsPage.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { usePrompts, useDeletePrompt } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { AddPromptDialog } from "./workspace/AddPromptDialog";
import type { PromptTemplate } from "@/lib/enrichments.types";

export function PromptsPage() {
  const { t } = useTranslation("prompts");
  const { toast } = useToast();
  const { data: prompts = [], isLoading } = usePrompts();
  const deleteMutation = useDeletePrompt();
  const [addOpen, setAddOpen] = useState(false);
  const [toDelete, setToDelete] = useState<PromptTemplate | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("error_referenced"), variant: "destructive" });
      } else {
        toast({ title: t("error_toast"), variant: "destructive" });
      }
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && prompts.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("col_name")}</TableHead>
                <TableHead>{t("col_language")}</TableHead>
                <TableHead>{t("col_metadata_key")}</TableHead>
                <TableHead>{t("col_result_type")}</TableHead>
                <TableHead>{t("col_description")}</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {prompts.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-sm">{p.name}</TableCell>
                  <TableCell>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {p.language}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-600">
                    {p.metadata_key}
                  </TableCell>
                  <TableCell>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                      p.result_type === "json"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-slate-100 text-slate-700"
                    }`}>
                      {p.result_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-slate-400 max-w-[200px] truncate">
                    {p.description ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(p)}
                      className="text-rose-600 hover:text-rose-700"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddPromptDialog open={addOpen} onOpenChange={setAddOpen} />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Ajouter la route `/prompts` dans `routes.tsx`**

Ajouter l'import :
```tsx
import { PromptsPage } from "@/pages/PromptsPage";
```

Ajouter dans `<Routes>` après `/models` :
```tsx
<Route path="/prompts" element={<PromptsPage />} />
```

- [ ] **Ajouter l'entrée Prompts dans `Sidebar.tsx`**

Ajouter l'import `FileCode` depuis lucide-react (ou `BookTemplate`).

Dans la section `Administration`, après `NavItem models`, ajouter :
```tsx
<NavItem to="/prompts" icon={<FileCode />} label={t("items.prompts")} />
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/PromptsPage.tsx \
        frontend/src/pages/workspace/AddPromptDialog.tsx \
        frontend/src/routes.tsx \
        frontend/src/components/Sidebar.tsx
git commit -m "feat(front): PromptsPage + AddPromptDialog + route + sidebar"
```

---

## Task 3 : WorkspaceTriggersTab + AddTriggerDialog + WorkspaceDetailPanel

**Files:**
- Create: `frontend/src/pages/workspace/WorkspaceTriggersTab.tsx`
- Create: `frontend/src/pages/workspace/AddTriggerDialog.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx`

- [ ] **Créer `frontend/src/pages/workspace/AddTriggerDialog.tsx`**

```tsx
import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateTrigger } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddTriggerDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const mutation = useCreateTrigger(workspaceName);
  const [extension, setExtension] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setExtension("");
  }

  const canSubmit =
    extension.trim().startsWith(".") &&
    extension.trim().length >= 2 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ extension: extension.trim().toLowerCase() });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t("add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_extension")}
            </Label>
            <Input
              value={extension}
              onChange={(e) => setExtension(e.target.value)}
              placeholder={t("field_extension_placeholder")}
              className="mt-1 font-mono"
            />
            <p className="mt-1 text-xs text-slate-400">{t("field_extension_help")}</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Créer `frontend/src/pages/workspace/WorkspaceTriggersTab.tsx`**

```tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, ChevronDown, ChevronRight, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import {
  useTriggers, useCreateTrigger, usePatchTrigger, useDeleteTrigger,
  useTriggerPrompts, useCreateTriggerPrompt, useDeleteTriggerPrompt,
} from "@/hooks/useEnrichments";
import { usePrompts } from "@/hooks/useEnrichments";
import { useLlmConfigs } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import { AddTriggerDialog } from "./AddTriggerDialog";
import type { Trigger } from "@/lib/enrichments.types";

interface TriggerRowProps {
  trigger: Trigger;
  workspaceName: string;
}

function TriggerPromptsPanel({ trigger, workspaceName }: TriggerRowProps) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const { data: triggerPrompts = [] } = useTriggerPrompts(workspaceName, trigger.id);
  const { data: allPrompts = [] } = usePrompts();
  const { data: llmConfigs = [] } = useLlmConfigs(workspaceName);
  const addPrompt = useCreateTriggerPrompt(workspaceName, trigger.id);
  const deletePrompt = useDeleteTriggerPrompt(workspaceName, trigger.id);

  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [selectedLlm, setSelectedLlm] = useState("");
  const [addOpen, setAddOpen] = useState(false);

  const nextOrder = triggerPrompts.length + 1;

  async function handleAddPrompt() {
    if (!selectedTemplate || !selectedLlm) return;
    await addPrompt.mutateAsync({
      template_id: selectedTemplate,
      llm_id: selectedLlm,
      order_index: nextOrder,
    });
    setSelectedTemplate("");
    setSelectedLlm("");
    setAddOpen(false);
  }

  return (
    <div className="border-t bg-slate-50 p-3 space-y-2">
      <p className="text-xs font-semibold text-slate-600">{t("prompts_title")}</p>
      {triggerPrompts.length === 0 ? (
        <p className="text-xs text-slate-400">{t("prompts_empty")}</p>
      ) : (
        <div className="space-y-1">
          {triggerPrompts.map((tp) => (
            <div key={tp.id} className="flex items-center gap-2 rounded bg-white border border-slate-200 px-3 py-1.5 text-xs">
              <span className="text-slate-400 w-5">{tp.order_index}.</span>
              <span className="font-medium text-slate-700 flex-1">{tp.template_name}</span>
              <span className="text-slate-400">{tp.llm_provider}/{tp.llm_model}</span>
              <Button
                variant="ghost"
                size="sm"
                className="h-6 px-1 text-rose-500 hover:text-rose-700"
                onClick={() => deletePrompt.mutate(tp.id)}
              >
                <Trash2 className="h-3 w-3" />
              </Button>
            </div>
          ))}
        </div>
      )}

      {!addOpen ? (
        <Button variant="outline" size="sm" onClick={() => setAddOpen(true)} className="text-xs">
          <Plus className="h-3 w-3 mr-1" />
          {t("add_prompt_btn")}
        </Button>
      ) : (
        <div className="space-y-2 rounded border border-slate-200 bg-white p-3">
          <p className="text-xs font-medium text-slate-600">{t("add_prompt_dialog_title")}</p>
          <Select value={selectedTemplate} onValueChange={setSelectedTemplate}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder={t("field_template")} />
            </SelectTrigger>
            <SelectContent>
              {allPrompts.map((p) => (
                <SelectItem key={p.id} value={p.id} className="text-xs">
                  {p.name} <span className="text-slate-400">({p.language})</span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Select value={selectedLlm} onValueChange={setSelectedLlm}>
            <SelectTrigger className="h-8 text-xs">
              <SelectValue placeholder={t("field_llm")} />
            </SelectTrigger>
            <SelectContent>
              {llmConfigs.filter((l) => l.enabled).map((l) => (
                <SelectItem key={l.id} value={l.id} className="text-xs font-mono">
                  {l.provider}/{l.model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
          <div className="flex gap-2">
            <Button size="sm" className="text-xs h-7" onClick={handleAddPrompt}
              disabled={!selectedTemplate || !selectedLlm || addPrompt.isPending}>
              {t("prompt_add_save")}
            </Button>
            <Button variant="ghost" size="sm" className="text-xs h-7" onClick={() => setAddOpen(false)}>
              {t("cancel")}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

interface Props {
  workspaceName: string;
}

export function WorkspaceTriggersTab({ workspaceName }: Props) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const { data: triggers = [], isLoading } = useTriggers(workspaceName);
  const patchMutation = usePatchTrigger(workspaceName);
  const deleteMutation = useDeleteTrigger(workspaceName);
  const [addOpen, setAddOpen] = useState(false);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [toDelete, setToDelete] = useState<Trigger | null>(null);

  function toggleExpand(id: string) {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  }

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("deleted_toast") });
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && triggers.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="rounded border border-slate-200 overflow-hidden divide-y divide-slate-200">
          {triggers.map((trigger) => (
            <div key={trigger.id}>
              <div className="flex items-center gap-3 px-4 py-3 bg-white">
                <button
                  type="button"
                  className="text-slate-400 hover:text-slate-600"
                  onClick={() => toggleExpand(trigger.id)}
                >
                  {expanded.has(trigger.id)
                    ? <ChevronDown className="h-4 w-4" />
                    : <ChevronRight className="h-4 w-4" />}
                </button>
                <span className="font-mono text-sm font-semibold text-slate-700 flex-1">
                  {trigger.extension}
                </span>
                <Switch
                  checked={trigger.enabled}
                  onCheckedChange={(enabled) =>
                    patchMutation.mutate({ triggerId: trigger.id, payload: { enabled } })
                  }
                />
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => setToDelete(trigger)}
                  className="text-rose-600 hover:text-rose-700"
                >
                  <Trash2 className="h-3.5 w-3.5" />
                </Button>
              </div>
              {expanded.has(trigger.id) && (
                <TriggerPromptsPanel trigger={trigger} workspaceName={workspaceName} />
              )}
            </div>
          ))}
        </div>
      )}

      <AddTriggerDialog
        workspaceName={workspaceName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
```

- [ ] **Modifier `WorkspaceDetailPanel.tsx`** — ajouter l'onglet Triggers

Ajouter l'import :
```tsx
import { WorkspaceTriggersTab } from "./WorkspaceTriggersTab";
```

Dans `<TabsList>`, après le trigger `playground`, ajouter :
```tsx
<TabsTrigger value="triggers">{t("tabs.triggers")}</TabsTrigger>
```

Après le `</TabsContent>` playground, ajouter :
```tsx
<TabsContent value="triggers" className="pt-4">
  <WorkspaceTriggersTab workspaceName={ws.name} />
</TabsContent>
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceTriggersTab.tsx \
        frontend/src/pages/workspace/AddTriggerDialog.tsx \
        frontend/src/pages/workspace/WorkspaceDetailPanel.tsx
git commit -m "feat(front): WorkspaceTriggersTab + AddTriggerDialog + onglet Triggers"
```
