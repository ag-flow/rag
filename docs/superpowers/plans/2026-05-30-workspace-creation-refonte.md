# Workspace Creation Refonte — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Réécrire le dialog de création de workspace pour utiliser des clés API déjà stockées dans Harpocrate (via le module provider_api_keys), supprimer le choix de coffre, et rendre la config reranking immuable (configurée une fois à la création).

**Architecture:** Nouveau schéma `WorkspaceCreateRequest` sans `api_key_vault` ni `api_key` en clair — le coffre MCP workspace utilise automatiquement le coffre par défaut, l'indexer référence une `provider_api_key` existante via son `harpo_path`. Le reranking est créé atomiquement à la création du workspace et ne peut plus être modifié ni supprimé. Nouveau endpoint `GET /api/admin/provider-keys/by-provider` filtré par owner.

**Prérequis :** Plan vault-ownership exécuté (migration 029, `owner_id`, `list_for_owner`).

**Tech Stack:** Python 3.12 / asyncpg / FastAPI / Pydantic v2 — React 18 / TypeScript strict / TanStack Query / react-hook-form / zod

---

## Structure des fichiers

### Backend (modifier)
- `backend/src/rag/schemas/admin.py`
- `backend/src/rag/services/workspaces.py`
- `backend/src/rag/api/admin.py`
- `backend/src/rag/api/admin_provider_keys.py`
- `backend/src/rag/services/provider_api_keys.py`

### Frontend (modifier)
- `frontend/src/lib/workspaces.types.ts` (ou équivalent)
- `frontend/src/lib/harpocrate-vaults.types.ts`
- `frontend/src/lib/harpocrate-vaults.ts`
- `frontend/src/hooks/useHarpocrateVaults.ts`
- `frontend/src/pages/workspace/CreateWorkspaceDialog.tsx`
- `frontend/src/pages/workspace/WorkspaceRerankTab.tsx`
- `frontend/src/i18n/fr/workspaces.json`
- `frontend/src/i18n/en/workspaces.json`

---

## Task 1 : Schemas backend

**Files:**
- Modify: `backend/src/rag/schemas/admin.py`

- [ ] **Remplacer `IndexerCreateSpec` et `WorkspaceCreateRequest`**

Dans `backend/src/rag/schemas/admin.py`, remplacer la classe `IndexerCreateSpec` et `WorkspaceCreateRequest` par :

```python
class IndexerCreateSpec(BaseModel):
    """Indexeur pour la création d'un workspace.

    api_key_ref est le harpo_path d'une provider_api_key existante.
    Le backend ne stocke rien dans Harpocrate — il référence une clé déjà présente.
    """

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None


class RerankCreateSpec(BaseModel):
    """Config reranking à la création d'un workspace (immuable après)."""

    model_config = ConfigDict(extra="forbid", protected_namespaces=())

    provider: str = Field(min_length=1)
    model: str = Field(min_length=1)
    api_key_ref: str | None = None
    base_url: str | None = None
    top_k_pre_rerank: int = Field(default=50, gt=0, le=500)


class WorkspaceCreateRequest(BaseModel):
    """Payload POST /workspaces."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_NAME_REGEX, max_length=63)
    indexer: IndexerCreateSpec
    rerank: RerankCreateSpec | None = None
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/schemas/admin.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/admin.py
git commit -m "feat(schemas): WorkspaceCreateRequest — api_key_ref direct + rerank optionnel"
```

---

## Task 2 : Service workspace — default vault + api_key_ref direct + rerank atomique

**Files:**
- Modify: `backend/src/rag/services/workspaces.py`

- [ ] **Modifier `create_workspace`**

Lis le fichier complet avant de modifier.

Objectif : la nouvelle `create_workspace` doit :
1. Utiliser le vault **par défaut** pour stocker l'api_key MCP du workspace (au lieu de `request.api_key_vault`)
2. Utiliser `request.indexer.api_key_ref` directement dans `indexer_configs` (ne plus écrire dans Harpocrate)
3. Si `request.rerank` est fourni : créer la config rerank dans la même transaction

**Changements dans la fonction `create_workspace` :**

a) Remplacer la récupération du vault par nom (`get_by_name`) par :

```python
vault = await harpocrate_vaults_service.get_default(conn)
if vault is None:
    raise VaultNotFoundForWorkspace("default")
```

b) Supprimer le bloc qui stocke `indexer.api_key` dans Harpocrate (`indexer_api_key_ref`).

c) Utiliser directement `request.indexer.api_key_ref` comme valeur pour `indexer_configs` :

```python
indexer_api_key_ref = request.indexer.api_key_ref
```

d) Dans la transaction, si `request.rerank` est fourni, créer la config rerank :

```python
if request.rerank:
    from rag.services.rerank_configs import upsert_rerank_config
    rerank = request.rerank
    await upsert_rerank_config(
        workspace_id,
        _config_pool=None,  # conn déjà acquise — adapter upsert_rerank_config
        provider=rerank.provider,
        model=rerank.model,
        api_key_ref=rerank.api_key_ref,
        base_url=rerank.base_url,
        top_k_pre_rerank=rerank.top_k_pre_rerank,
        conn=conn,
    )
```

Note : si `upsert_rerank_config` n'accepte pas une `conn` externe, ajouter un paramètre optionnel `conn` pour passer une connexion existante et éviter d'en acquérir une nouvelle dans la même transaction. Lis `backend/src/rag/services/rerank_configs.py` pour comprendre sa signature exacte.

- [ ] **Vérifier les imports et lint**

```bash
cd backend && uv run ruff check src/rag/services/workspaces.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/services/workspaces.py
git commit -m "feat(services): workspace.create — default vault + api_key_ref direct + rerank atomique"
```

---

## Task 3 : Supprimer les routes rerank mutables

**Files:**
- Modify: `backend/src/rag/api/admin.py`

- [ ] **Supprimer PUT et DELETE `/workspaces/{name}/rerank`**

Dans `backend/src/rag/api/admin.py` :

1. Supprimer entièrement la route `PUT /workspaces/{name}/rerank` (qui commence à la ligne annotée `@router.put("/workspaces/{name}/rerank")`)

2. Supprimer entièrement la route `DELETE /workspaces/{name}/rerank` (qui commence à `@router.delete("/workspaces/{name}/rerank",`)

3. Conserver uniquement `GET /workspaces/{name}/rerank`

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin.py
```

- [ ] **Vérifier que les routes disparaissent**

```bash
cd backend && python -c "from rag.api.admin import build_admin_router; r = build_admin_router(); print([str(r.url_path) for r in r.routes if 'rerank' in str(r)])" 2>/dev/null || echo "import ok"
```

- [ ] **Commit**

```bash
git add backend/src/rag/api/admin.py
git commit -m "feat(api): supprimer PUT+DELETE /workspaces/{name}/rerank — rerank immuable"
```

---

## Task 4 : Endpoint GET /api/admin/provider-keys/by-provider

**Files:**
- Modify: `backend/src/rag/schemas/provider_api_keys.py`
- Modify: `backend/src/rag/services/provider_api_keys.py`
- Modify: `backend/src/rag/api/admin_provider_keys.py`

- [ ] **Ajouter `ProviderApiKeyWithVault` dans les schemas**

Dans `backend/src/rag/schemas/provider_api_keys.py`, ajouter :

```python
class ProviderApiKeyWithVault(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    key_id: str
    label: str
    provider: str
    harpo_path: str
    vault_name: str
    vault_label: str
    created_at: datetime
```

- [ ] **Ajouter `list_provider_keys_by_provider` dans le service**

Dans `backend/src/rag/services/provider_api_keys.py`, ajouter :

```python
async def list_provider_keys_by_provider(
    conn: asyncpg.Connection,
    *,
    owner_id: str,
    provider: str,
) -> list[dict]:
    """Retourne les clés pour `provider` des vaults accessibles à `owner_id`.

    Vaults éligibles : is_default = true OU owner_id = $owner_id.
    """
    rows = await conn.fetch(
        "SELECT pk.id, pk.key_id, pk.label, pk.provider, pk.harpo_path, "
        "pk.created_at, v.name AS vault_name, v.label AS vault_label "
        "FROM provider_api_keys pk "
        "JOIN harpocrate_vaults v ON v.id = pk.vault_id "
        "WHERE pk.provider = $1 "
        "AND (v.is_default = true OR v.owner_id = $2) "
        "ORDER BY v.name, pk.key_id",
        provider,
        owner_id,
    )
    return [dict(r) for r in rows]
```

- [ ] **Ajouter la route dans le router**

Dans `backend/src/rag/api/admin_provider_keys.py`, ajouter :

```python
from rag.auth.owner import get_current_owner_id
from rag.schemas.provider_api_keys import ProviderApiKeyWithVault
from rag.services.provider_api_keys import list_provider_keys_by_provider

# Router séparé sans vault_id dans le prefix
router_global = APIRouter(
    prefix="/api/admin/provider-keys",
    tags=["admin-provider-keys"],
    dependencies=[Depends(require_master_key_or_authenticated_admin)],
)


@router_global.get("/by-provider", response_model=list[ProviderApiKeyWithVault])
async def list_by_provider(
    provider: str,
    request: Request,
) -> list[ProviderApiKeyWithVault]:
    pool = _pool(request)
    owner_id = get_current_owner_id(request)
    async with pool.acquire() as conn:
        rows = await list_provider_keys_by_provider(conn, owner_id=owner_id, provider=provider)
    return [ProviderApiKeyWithVault.model_validate(r) for r in rows]
```

- [ ] **Enregistrer `router_global` dans `main.py`**

Dans `backend/src/rag/main.py`, après `from rag.api.admin_provider_keys import router as admin_provider_keys_router` :

```python
from rag.api.admin_provider_keys import router_global as admin_provider_keys_global_router
```

Après `app.include_router(admin_provider_keys_router)` :

```python
app.include_router(admin_provider_keys_global_router)
```

- [ ] **Lint**

```bash
cd backend && uv run ruff check src/rag/api/admin_provider_keys.py src/rag/services/provider_api_keys.py src/rag/schemas/provider_api_keys.py src/rag/main.py
```

- [ ] **Commit**

```bash
git add backend/src/rag/schemas/provider_api_keys.py \
        backend/src/rag/services/provider_api_keys.py \
        backend/src/rag/api/admin_provider_keys.py \
        backend/src/rag/main.py
git commit -m "feat(api): GET /provider-keys/by-provider — filtré par owner"
```

---

## Task 5 : Frontend — types + API client + hook

**Files:**
- Modify: `frontend/src/lib/harpocrate-vaults.types.ts`
- Modify: `frontend/src/lib/harpocrate-vaults.ts`
- Modify: `frontend/src/hooks/useHarpocrateVaults.ts`

- [ ] **Ajouter `ProviderApiKeyWithVault` dans les types**

Dans `frontend/src/lib/harpocrate-vaults.types.ts`, ajouter à la fin :

```typescript
export type ProviderApiKeyWithVault = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
  created_at: string;
};
```

- [ ] **Ajouter la fonction API dans `harpocrate-vaults.ts`**

Ajouter l'import et la méthode dans `harpocrateVaultsApi` :

```typescript
import type {
  // ...existants...
  ProviderApiKeyWithVault,
} from "@/lib/harpocrate-vaults.types";

// Dans harpocrateVaultsApi :
  listProviderKeysByProvider: (provider: string) =>
    api.get<ProviderApiKeyWithVault[]>(
      `/api/admin/provider-keys/by-provider?provider=${encodeURIComponent(provider)}`
    ),
```

- [ ] **Ajouter `useProviderKeysByProvider` dans les hooks**

Dans `frontend/src/hooks/useHarpocrateVaults.ts`, ajouter à la fin :

```typescript
export function useProviderKeysByProvider(provider: string | null) {
  return useQuery({
    queryKey: ["provider-keys-by-provider", provider],
    queryFn: () => harpocrateVaultsApi.listProviderKeysByProvider(provider!),
    enabled: !!provider,
    staleTime: 30_000,
  });
}
```

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/lib/harpocrate-vaults.types.ts \
        frontend/src/lib/harpocrate-vaults.ts \
        frontend/src/hooks/useHarpocrateVaults.ts
git commit -m "feat(front): ProviderApiKeyWithVault type + API client + useProviderKeysByProvider"
```

---

## Task 6 : CreateWorkspaceDialog — réécriture

**Files:**
- Modify: `frontend/src/pages/workspace/CreateWorkspaceDialog.tsx`
- Modify: `frontend/src/lib/validators.ts` (ou là où se trouve `workspaceCreateSchema`)
- Modify: `frontend/src/i18n/fr/workspaces.json`
- Modify: `frontend/src/i18n/en/workspaces.json`

- [ ] **Mettre à jour le schéma de validation Zod**

Lis `frontend/src/lib/validators.ts` pour trouver `workspaceCreateSchema`. Le remplacer par :

```typescript
import { z } from "zod";

const indexerSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  api_key_ref: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
});

const rerankSchema = z.object({
  provider: z.string().min(1),
  model: z.string().min(1),
  api_key_ref: z.string().nullable().optional(),
  base_url: z.string().nullable().optional(),
  top_k_pre_rerank: z.number().int().min(1).max(500).default(50),
});

export const workspaceCreateSchema = z.object({
  name: z.string().regex(/^[a-z][a-z0-9_-]{0,62}$/),
  indexer: indexerSchema,
  rerank: rerankSchema.nullable().optional(),
});
```

- [ ] **Ajouter les clés i18n dans `workspaces.json` (FR)**

Dans `frontend/src/i18n/fr/workspaces.json`, dans l'objet `form`, ajouter :

```json
"indexer_section": "Vectorisation",
"rerank_section": "Reranking (optionnel)",
"api_key_ref": "Clé API",
"api_key_ref_placeholder": "Sélectionner une clé",
"api_key_ref_none": "Aucune clé disponible pour ce provider — ajoutez-en une dans un coffre Harpocrate",
"top_k": "top_k pré-rerank",
"top_k_default": "50"
```

- [ ] **Ajouter les clés i18n dans `workspaces.json` (EN)**

```json
"indexer_section": "Vectorisation",
"rerank_section": "Reranking (optional)",
"api_key_ref": "API key",
"api_key_ref_placeholder": "Select a key",
"api_key_ref_none": "No key available for this provider — add one in a Harpocrate vault",
"top_k": "top_k pre-rerank",
"top_k_default": "50"
```

- [ ] **Réécrire `CreateWorkspaceDialog.tsx`**

Remplacer le contenu entier du fichier par :

```tsx
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateWorkspace } from "@/hooks/useWorkspaces";
import { useModels } from "@/hooks/useModels";
import { useProviderKeysByProvider } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { workspaceCreateSchema } from "@/lib/validators";

type FormData = z.infer<typeof workspaceCreateSchema>;

const BASE_URL_PROVIDERS = ["ollama", "azure-openai"];
const NO_KEY_PROVIDERS = ["ollama"];

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (ws: { name: string }) => void;
}

function ProviderModelBlock({
  prefix,
  label,
  form,
  models,
}: {
  prefix: "indexer" | "rerank";
  label: string;
  form: ReturnType<typeof useForm<FormData>>;
  models: { provider: string; model: string }[];
}) {
  const { t } = useTranslation("workspaces");
  const provider = useWatch({ control: form.control, name: `${prefix}.provider` as any });
  const providers = [...new Set(models.map((m) => m.provider))].sort();
  const filteredModels = models.filter((m) => m.provider === provider).map((m) => m.model);
  const needsUrl = BASE_URL_PROVIDERS.includes(provider);
  const needsKey = !NO_KEY_PROVIDERS.includes(provider);
  const { data: keys = [] } = useProviderKeysByProvider(needsKey ? provider : null);

  return (
    <div className="space-y-3 rounded-md border bg-slate-50 p-4">
      <div className="text-xs font-bold uppercase tracking-wide text-slate-600">{label}</div>

      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name={`${prefix}.provider` as any}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("form.provider")}</FormLabel>
              <Select
                onValueChange={(v) => {
                  field.onChange(v);
                  const firstModel = models.find((m) => m.provider === v)?.model ?? "";
                  form.setValue(`${prefix}.model` as any, firstModel);
                  form.setValue(`${prefix}.api_key_ref` as any, null);
                }}
                value={field.value}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={t("form.provider")} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name={`${prefix}.model` as any}
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
                  {filteredModels.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {needsUrl && (
        <FormField
          control={form.control}
          name={`${prefix}.base_url` as any}
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t("form.base_url")}{" "}
                <span className="font-normal text-slate-400">{t("form.base_url_optional")}</span>
              </FormLabel>
              <FormControl>
                <Input
                  placeholder="http://192.168.10.80:11434"
                  {...field}
                  value={field.value ?? ""}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {needsKey && (
        <FormField
          control={form.control}
          name={`${prefix}.api_key_ref` as any}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("form.api_key_ref")}</FormLabel>
              {keys.length === 0 ? (
                <p className="text-xs text-amber-600">{t("form.api_key_ref_none")}</p>
              ) : (
                <Select onValueChange={field.onChange} value={field.value ?? ""}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder={t("form.api_key_ref_placeholder")} />
                    </SelectTrigger>
                  </FormControl>
                  <SelectContent>
                    {keys.map((k) => (
                      <SelectItem key={k.id} value={k.harpo_path}>
                        <span className="font-medium">{k.label}</span>
                        <span className="ml-2 text-xs text-slate-400">
                          {k.vault_label} · {k.key_id}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}

export function CreateWorkspaceDialog({ open, onOpenChange, onCreated }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const createMutation = useCreateWorkspace();
  const { data: models = [] } = useModels();
  const defaultProvider = [...new Set(models.map((m) => m.provider))].sort()[0] ?? "openai";
  const defaultModel = models.find((m) => m.provider === defaultProvider)?.model ?? "";

  const form = useForm<FormData>({
    resolver: zodResolver(workspaceCreateSchema),
    defaultValues: {
      name: "",
      indexer: { provider: defaultProvider, model: defaultModel, api_key_ref: null, base_url: null },
      rerank: null,
    },
  });

  async function onSubmit(values: FormData) {
    try {
      const resp = await createMutation.mutateAsync({
        name: values.name,
        indexer: {
          provider: values.indexer.provider,
          model: values.indexer.model,
          api_key_ref: values.indexer.api_key_ref ?? null,
          base_url: values.indexer.base_url ?? null,
        },
        rerank: values.rerank
          ? {
              provider: values.rerank.provider,
              model: values.rerank.model,
              api_key_ref: values.rerank.api_key_ref ?? null,
              base_url: values.rerank.base_url ?? null,
              top_k_pre_rerank: values.rerank.top_k_pre_rerank,
            }
          : undefined,
      });
      toast({ title: t("toasts.created", { name: resp.name }) });
      onOpenChange(false);
      form.reset();
      onCreated?.({ name: resp.name });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  const [showRerank, setShowRerank] = useState(false);

  function handleToggleRerank() {
    if (showRerank) {
      form.setValue("rerank", null);
    } else {
      form.setValue("rerank", {
        provider: defaultProvider,
        model: defaultModel,
        api_key_ref: null,
        base_url: null,
        top_k_pre_rerank: 50,
      });
    }
    setShowRerank(!showRerank);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[540px] max-h-[85vh] overflow-y-auto">
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
                    <Input placeholder="workspace1" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <ProviderModelBlock
              prefix="indexer"
              label={t("form.indexer_section")}
              form={form}
              models={models}
            />

            {showRerank ? (
              <>
                <ProviderModelBlock
                  prefix="rerank"
                  label={t("form.rerank_section")}
                  form={form}
                  models={models}
                />
                <FormField
                  control={form.control}
                  name="rerank.top_k_pre_rerank"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.top_k")}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={500}
                          {...field}
                          onChange={(e) => field.onChange(parseInt(e.target.value, 10))}
                          className="w-32"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button type="button" variant="ghost" size="sm" onClick={handleToggleRerank}
                  className="text-slate-500 text-xs">
                  {t("form.rerank_remove")}
                </Button>
              </>
            ) : (
              <Button type="button" variant="outline" size="sm" onClick={handleToggleRerank}>
                + {t("form.rerank_section")}
              </Button>
            )}

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

Note : ajouter `import { useState } from "react"` en tête.

- [ ] **Vérifier TypeScript**

```bash
cd frontend && npx tsc --noEmit
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/CreateWorkspaceDialog.tsx \
        frontend/src/lib/validators.ts \
        frontend/src/i18n/fr/workspaces.json \
        frontend/src/i18n/en/workspaces.json
git commit -m "feat(front): CreateWorkspaceDialog — sélect clé API + reranking optionnel"
```

---

## Task 7 : WorkspaceRerankTab — lecture seule

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceRerankTab.tsx`

- [ ] **Réécrire `WorkspaceRerankTab.tsx` en lecture seule**

Remplacer le contenu entier du fichier par :

```tsx
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useRerankConfig } from "@/hooks/useRerank";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceRerankTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useRerankConfig(workspace.name, enabled);

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-slate-900">{t("rerank.title")}</h3>

      {!data ? (
        <p className="text-sm text-slate-500">{t("rerank.description.empty")}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">{t("rerank.fields.provider")}</dt>
          <dd className="font-mono">{data.provider}</dd>
          <dt className="text-slate-500">{t("rerank.fields.model")}</dt>
          <dd className="font-mono">{data.model}</dd>
          <dt className="text-slate-500">{t("rerank.fields.baseUrl")}</dt>
          <dd className="font-mono">{data.base_url ?? "—"}</dd>
          <dt className="text-slate-500">{t("rerank.fields.apiKeyRef")}</dt>
          <dd className="font-mono">{data.api_key_ref ?? "—"}</dd>
          <dt className="text-slate-500">{t("rerank.fields.topK")}</dt>
          <dd className="font-mono">{data.top_k_pre_rerank}</dd>
        </dl>
      )}

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("rerank.warning")}</p>
      </div>
    </div>
  );
}
```

- [ ] **Vérifier TypeScript + lint**

```bash
cd frontend && npx tsc --noEmit && npm run lint
```

- [ ] **Commit**

```bash
git add frontend/src/pages/workspace/WorkspaceRerankTab.tsx
git commit -m "feat(front): WorkspaceRerankTab — lecture seule (reranking immuable)"
```
