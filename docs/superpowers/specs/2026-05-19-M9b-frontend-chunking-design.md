# M9b — Chunking frontend (onglet `Chunking` dans WorkspaceDetailPanel)

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § « Amélioration du chunking ».
> **Backend pré-requis** : M9 (livré). API `GET/PUT /api/admin/workspaces/{name}/chunking-config` opérationnelle.
> **Pattern de référence** : M8b (frontend rerank), commits c103c5a et précédents.
> **Hors-scope explicite** : nouvelles stratégies (markdown, code) — l'UI les supportera quand le backend les ajoutera.

---

## 1. Contexte et motivation

M9 a livré l'infrastructure backend du chunking : table `chunking_configs` par workspace, endpoints REST avec confirm-then-reindex pour les changements destructifs, DTO Pydantic. Aujourd'hui la config n'est manipulable que par appel API direct — aucune visibilité ni édition côté IHM admin.

M9b ajoute le **6ᵉ onglet** dans `WorkspaceDetailPanel` (`Chunking`), aligné stylistiquement et structurellement sur l'onglet `Rerank` livré par M8b. La principale différence d'ergonomie : la config chunking est **obligatoire** (toujours présente après création workspace, pas de DELETE) et **un changement de paramètres déclenche un flow de confirmation réindexation** quand le workspace contient des documents indexés.

---

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Config visible dans un onglet dédié `Chunking` du `WorkspaceDetailPanel` | Symétrique avec `Rerank` et `Modèle` — paradigme rodé |
| D2 | Pas de bouton DELETE | Row obligatoire, FK cascade depuis workspace ; spec M9 §D2 |
| D3 | Strategy via `Select` à une seule option (`paragraph`) dès maintenant | Prêt pour les jalons futurs sans refonte UI ; le pattern Select est cohérent avec `rerank.provider` |
| D4 | Flow 409 **optimiste** : PUT direct → intercept 409 → AlertDialog → re-PUT `?confirm=true` | Le serveur fait l'autorité ; le payload 409 contient `current`/`new` pour afficher un diff précis. Pas de docs_count côté front |
| D5 | Feedback 202 = **toast simple** | Symétrique M8b ; l'utilisateur consulte l'onglet `Jobs` s'il veut suivre |
| D6 | Pas de redirection automatique vers `Jobs` | Discrétion d'usage ; l'utilisateur reste maître de sa navigation |
| D7 | Tests symétriques M8b (composant + hooks + schema + alert + i18n) | Couverture rodée, robuste, sans coût supplémentaire |
| D8 | Pas de Playwright / E2E | Vitest + `vi.mock` du module `lib/chunking.ts` suffit ; pattern projet établi |
| D9 | Pas de modification du backend | M9 backend complet ; M9b est purement frontend |
| D10 | Validations Zod côté front répliquent les contraintes Pydantic backend | `min_chars < max_chars`, `overlap_chars < max_chars`, `max_chars ≥ 1` ; défense en profondeur |
| D11 | Helper `isChunkingChangeRequiresReindex(body)` colocale dans `lib/chunking.ts` | Type guard explicite ; évite duplication dans le composant |

---

## 3. Inventaire des fichiers

### 3.1 Nouveaux fichiers

| Fichier | Responsabilité |
|---|---|
| `frontend/src/lib/chunking.types.ts` | Types miroir des DTOs Pydantic : `ChunkingConfig`, `ChunkingSpec`, `ChunkingStrategy`, `ChunkingChangeRequiresReindexBody` |
| `frontend/src/lib/chunking.ts` | API client : `chunkingApi.get`, `chunkingApi.upsert(name, payload, confirm)` retournant `UpsertChunkingResult` discriminé ; helper `isChunkingChangeRequiresReindex` |
| `frontend/src/hooks/useChunking.ts` | Hooks React Query : `useChunkingConfig`, `useUpsertChunkingConfig` |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | Composant onglet : form + état dialog + dispatch flows |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` | Schema Zod + constantes (`CHUNKING_STRATEGIES`, `DEFAULT_CHUNKING_FORM`) |
| `frontend/src/pages/workspace/ChunkingConfirmReindexAlert.tsx` | `AlertDialog` shadcn/ui pour la confirmation 409 |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx` | Tests composant — 10+ scénarios couvrant tous les flows |
| `frontend/src/pages/workspace/__tests__/ChunkingConfirmReindexAlert.test.tsx` | Tests alert dialog |

### 3.2 Fichiers modifiés

| Fichier | Modification |
|---|---|
| `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx` | Ajout du 6ᵉ `TabsTrigger value="chunking"` + `TabsContent` |
| `frontend/src/i18n/fr.json` | Ajout section `chunking.*` (titre, description, fields, errors, save, reindex.dialog, warning) + `tabs.chunking` |
| `frontend/src/i18n/en.json` | Traduction symétrique |
| `frontend/src/lib/api.ts` | Si absent : ajout helper `putRaw(url, body)` retournant la `Response` brute (lecture status code 200/202/204) |

---

## 4. Types & API client

### 4.1 `lib/chunking.types.ts`

```ts
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

### 4.2 `lib/chunking.ts`

```ts
import { api } from "@/lib/api";
import type {
  ChunkingConfig,
  ChunkingSpec,
  ChunkingChangeRequiresReindexBody,
} from "@/lib/chunking.types";
import type { JobResponse } from "@/lib/jobs.types";

const base = (name: string) => `/api/admin/workspaces/${name}/chunking-config`;

export type UpsertChunkingResult =
  | { status: "no_change" }
  | { status: "updated"; config: ChunkingConfig }
  | { status: "reindex_triggered"; job: JobResponse };

export const chunkingApi = {
  get: (name: string) => api.get<ChunkingConfig>(base(name)),

  upsert: async (
    name: string,
    payload: ChunkingSpec,
    confirm: boolean = false,
  ): Promise<UpsertChunkingResult> => {
    const url = confirm ? `${base(name)}?confirm=true` : base(name);
    const res = await api.putRaw(url, payload);
    if (res.status === 204) return { status: "no_change" };
    if (res.status === 200)
      return { status: "updated", config: (await res.json()) as ChunkingConfig };
    if (res.status === 202)
      return { status: "reindex_triggered", job: (await res.json()) as JobResponse };
    throw new Error(`Unexpected status ${res.status}`);
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

### 4.3 Extension `lib/api.ts` (conditionnelle)

Si `api.putRaw` n'existe pas :

```ts
export const api = {
  // ... helpers existants
  putRaw: (url: string, body: unknown): Promise<Response> =>
    fetch(url, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
      credentials: "include",
    }),
};
```

Le code 4xx/5xx remonte une `ApiError` via le wrapper standard si on passe par `api.put` ; `putRaw` reste bas-niveau pour le besoin spécifique du discriminant 200/202/204.

**Décision d'implémentation** : la Task 1 du plan inspectera `lib/api.ts` pour choisir entre (a) ajouter `putRaw`, ou (b) lire le status code via une instrumentation différente (par exemple un wrapper qui throw seulement sur 4xx/5xx et retourne le body sur 2xx). À trancher au moment de l'implémentation selon le code existant.

---

## 5. Hooks React Query

### 5.1 `hooks/useChunking.ts`

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { chunkingApi, type UpsertChunkingResult } from "@/lib/chunking";
import type { ChunkingConfig, ChunkingSpec } from "@/lib/chunking.types";

export function useChunkingConfig(name: string, enabled: boolean) {
  return useQuery<ChunkingConfig>({
    queryKey: ["workspace", name, "chunking"],
    queryFn: () => chunkingApi.get(name),
    enabled,
  });
}

type UpsertVars = { payload: ChunkingSpec; confirm: boolean };

export function useUpsertChunkingConfig(name: string) {
  const qc = useQueryClient();
  return useMutation<UpsertChunkingResult, Error, UpsertVars>({
    mutationFn: ({ payload, confirm }) => chunkingApi.upsert(name, payload, confirm),
    onSuccess: (result) => {
      if (result.status !== "no_change") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "chunking"] });
      }
      if (result.status === "reindex_triggered") {
        void qc.invalidateQueries({ queryKey: ["workspace", name, "jobs"] });
      }
    },
  });
}
```

**Notes** :
- Pas d'interception du 409 dans le hook — le composant gère ce cas via `onError` pour pouvoir alimenter le dialog avec `current`/`new` du payload.
- Pas de `useDeleteChunkingConfig` — la row est obligatoire.

---

## 6. Composants UI

### 6.1 `WorkspaceChunkingTab.schema.ts`

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

### 6.2 `WorkspaceChunkingTab.tsx` — squelette comportemental

```tsx
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
    } else {
      toast({ title: t("chunking.reindex.triggered") });
    }
    form.reset(form.getValues());
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

  if (isLoading || !data) return <LoadingSpinner />;

  // JSX : titre + form (strategy select + 3 inputs number) + boutons + warning + ChunkingConfirmReindexAlert
  return ( /* … */ );
}
```

### 6.3 `ChunkingConfirmReindexAlert.tsx`

Pattern `AlertDialog` shadcn/ui (cf. `DeleteRerankAlert.tsx`).

Props :
```ts
type Props = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  current: string;   // ex: "paragraph (max=2000, min=200, overlap=200)"
  next: string;      // ex: "paragraph (max=1500, min=100, overlap=150)"
  onConfirm: () => void;
  pending: boolean;
};
```

Body affiche les 2 strings verbatim depuis le payload 409. Bouton "Réindexer maintenant" déclenche `onConfirm` (couleur d'emphase, comme une action destructive). Bouton "Annuler" appelle `onOpenChange(false)`.

### 6.4 Intégration `WorkspaceDetailPanel.tsx`

```tsx
<TabsTrigger value="chunking">{t("tabs.chunking")}</TabsTrigger>
…
<TabsContent value="chunking" className="pt-4">
  <WorkspaceChunkingTab workspace={ws} enabled={activeTab === "chunking"} />
</TabsContent>
```

Position : juste après `rerank`, dans l'ordre actuel `detail → sources → jobs → model → rerank → chunking`.

---

## 7. i18n

### 7.1 `frontend/src/i18n/fr.json`

Top-level `tabs.chunking` : `"Chunking"`.

Section `workspace.chunking.*` :

```json
{
  "chunking": {
    "title": "Configuration du chunking",
    "badgeMandatory": "obligatoire",
    "description": "Stratégie de découpage des documents avant indexation. Modifier ces paramètres nécessite une réindexation complète du workspace.",
    "warning": "Modifier ces paramètres rend les chunks existants incohérents avec les nouveaux embeddings. Une réindexation complète sera demandée.",
    "fields": {
      "strategy": "Stratégie",
      "strategyHelp": { "paragraph": "Découpage par paragraphes avec coalesce des petits et split des gros." },
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
}
```

### 7.2 `frontend/src/i18n/en.json`

Traduction symétrique mots-pour-mots des clés ci-dessus.

---

## 8. Error handling — matrice complète

| Scénario | HTTP | Action UI |
|---|---|---|
| GET 200 | 200 | form pré-rempli, dirty=false |
| GET 404 (workspace inconnu) | 404 | toast erreur générique (ne devrait pas arriver — l'onglet n'est rendu que pour un workspace existant) |
| PUT no-change | 204 | toast `chunking.save.noChange`, form reset à l'état soumis |
| PUT change + docs=0 | 200 | toast `chunking.save.success`, form mis à jour |
| PUT change + docs>0 sans confirm | 409 + `chunking_change_requires_reindex` | ouverture `ChunkingConfirmReindexAlert` avec `current` + `new` du payload |
| PUT change + docs>0 avec confirm | 202 + JobResponse | toast `chunking.reindex.triggered`, form mis à jour, dialog fermé, invalidation queries `chunking` + `jobs` |
| PUT 422 (Pydantic) | 422 | toast erreur — Zod côté front empêche normalement ce cas |
| Erreur réseau / 500 | * | toast `chunking.save.error` |

Le state `confirmReindex` est cleanup sur succès **et** sur erreur (pas de dialog zombie).

---

## 9. Accessibilité

- Chaque `Input` lié à un `<label htmlFor=…>` (pattern M8b).
- `AlertDialog` shadcn/ui gère focus trap + `aria-labelledby` nativement.
- Messages d'erreur sous chaque champ : `aria-live="polite"` sur le container parent.
- Bouton "Réindexer maintenant" : style d'emphase (rouge ou amber) signalant l'action destructive.

---

## 10. Tests

Pattern symétrique à M8b — Vitest + React Testing Library + `vi.mock` pour `lib/chunking.ts`.

### 10.1 `__tests__/WorkspaceChunkingTab.schema.test.ts`

- Happy path : `DEFAULT_CHUNKING_FORM` valide
- `max_chars < 1` → error
- `min_chars >= max_chars` → error path `["min_chars"]`, message `"min_lt_max"`
- `overlap_chars >= max_chars` → error path `["overlap_chars"]`, message `"overlap_lt_max"`
- `min_chars = 0` valide
- `overlap_chars = 0` valide
- Coerce string → number

### 10.2 `__tests__/chunking.test.ts` (API client)

- `upsert` → `{status: "no_change"}` quand 204
- `upsert` → `{status: "updated", config}` quand 200
- `upsert` → `{status: "reindex_triggered", job}` quand 202
- `upsert` propage `ApiError` sur 409
- URL inclut `?confirm=true` quand `confirm=true`
- URL sans query quand `confirm=false`

### 10.3 `__tests__/useChunking.test.ts`

- `useChunkingConfig` retourne data sur 200
- `useChunkingConfig` propage 404
- `useUpsertChunkingConfig` invalide `["workspace", name, "chunking"]` sur `updated`
- `useUpsertChunkingConfig` invalide `chunking` + `jobs` sur `reindex_triggered`
- `useUpsertChunkingConfig` n'invalide rien sur `no_change`

### 10.4 `__tests__/WorkspaceChunkingTab.test.tsx`

- Loading spinner pendant fetch
- Form pré-rempli avec la config actuelle
- Submit sans modification → toast `noChange` (mock 204)
- Submit avec modification, docs=0 → toast `success` + form mis à jour (mock 200)
- Submit avec modification, docs>0 → dialog ouvert avec `current` et `new` du payload 409
- Clic "Réindexer maintenant" → 2ème mutation `confirm: true` → toast `reindex.triggered` + dialog fermé
- Clic "Annuler" dans le dialog → dialog fermé, pas de mutation
- Erreur Zod (min ≥ max) → message d'erreur sous l'input, pas de submit
- Bouton "Enregistrer" disabled tant que form clean
- Bouton "Annuler" reset au DB

### 10.5 `__tests__/ChunkingConfirmReindexAlert.test.tsx`

- Affiche `current` et `next` passés en props
- Clic confirm → `onConfirm` appelé
- Clic cancel → `onOpenChange(false)` appelé
- Bouton confirm disabled quand `pending=true`
- Ne rend rien quand `open=false`

### 10.6 i18n

Vérification que les clés ajoutées sont présentes dans **les deux** locales (test automatique si déjà rodé sur M8b ; sinon check manuel à la self-review).

### 10.7 Pas de tests E2E backend↔frontend

L'intégration backend est testée séparément (M9 backend). Pattern projet : Vitest + mocks.

---

## 11. Plan de livraison et numérotation

- **M9b** = ce jalon (frontend chunking).
- **M9c+** ou jalons distincts : implémenter les chunkers `markdown` et `code` (backend) + adapter le `Select` strategy frontend.

Découpage des tâches au plan d'implémentation (rédigé après validation de la spec) :

1. Types + API client + helper `isChunkingChangeRequiresReindex` + (si nécessaire) `api.putRaw`
2. Hooks `useChunkingConfig` + `useUpsertChunkingConfig` + tests
3. i18n FR + EN (clés `tabs.chunking` + section `chunking.*`)
4. Schema Zod + tests
5. Composant `ChunkingConfirmReindexAlert` + tests
6. Composant `WorkspaceChunkingTab` + tests (form + flows)
7. Intégration dans `WorkspaceDetailPanel`
8. Smoke complet : `npm run lint`, `npx tsc --noEmit`, `npm test`

---

## 12. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| `api.putRaw` absent dans `lib/api.ts` | Task 1 du plan vérifie et ajoute le helper si nécessaire ; documenté en §4.3 |
| Le composant doit lire le payload de l'`ApiError` 409, type-safe | Helper `isChunkingChangeRequiresReindex` colocale, typeguard explicite |
| Risque que `current` / `next` du payload 409 changent de format côté backend | Le frontend les affiche **verbatim** sans parser ; tout changement backend reste lisible à l'écran (worst case : présentation cosmétique) |
| Cas où l'utilisateur ferme le dialog avant la fin de la mutation | Le state `confirmReindex` est cleanup en `finally` logique (sur success + error) ; le `pending` du bouton empêche les double-clics |
| Double-submit (clic rapide sur "Enregistrer") | `upsert.isPending` désactive le bouton "Enregistrer" |
| Form dirty mais utilisateur navigue ailleurs | Hors-scope M9b — pattern M8b ne propose pas de "leave guard" et on reste cohérent |

---

## 13. Hors-scope explicite

- Aucun nouveau chunker (markdown, code) — jalons distincts.
- Pas d'historique des changements de config (audit log) — non demandé.
- Pas d'affichage de `extras` côté form — vide pour `paragraph`, montré uniquement si une stratégie future en a besoin.
- Pas de leave-guard sur form dirty — cohérent avec M8b.
- Pas de Playwright / Cypress — pattern Vitest projet.
- Pas de redirection automatique vers `Jobs` après 202 — décision D6.
