# M8b — Frontend Rerank (onglet WorkspaceDetailPanel)

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § Reranking — frontend annoncé comme jalon M8b.
> **Prérequis** : M8 (endpoints `GET/PUT/DELETE /api/admin/workspaces/{name}/rerank` livrés), M7b (pattern form Zod + react-hook-form), M6 (`WorkspaceDetailPanel` + Tabs).

## 1. Contexte et motivation

Le backend M8 expose une configuration rerank **par workspace** via 3 endpoints admin :

- `GET /api/admin/workspaces/{name}/rerank` → 200 `RerankConfigResponse` ou 404 `rerank_not_configured`.
- `PUT /api/admin/workspaces/{name}/rerank` → 200 (upsert idempotent).
- `DELETE /api/admin/workspaces/{name}/rerank` → 204 (idempotent).

Sans frontend, la seule façon de configurer un reranker est via `curl` ou un client HTTP. Ce jalon livre l'IHM admin : un onglet `Rerank` dans `WorkspaceDetailPanel` permettant aux administrateurs de visualiser, créer, modifier ou supprimer la config rerank d'un workspace.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Nouvel **onglet "Rerank"** dans `WorkspaceDetailPanel` (5e position après Détail/Sources/Jobs/Modèle) | Annoncé tel quel dans `specs/09-roadmap.md`. Place naturelle : le rerank est scopé au workspace. |
| D2 | **Form unifié** (pattern `OidcConfigPage`) : pas de mode lecture/édition séparé | Un seul utilisateur cible (admin), pas de valeur à un état intermédiaire. Cohérent avec le pattern singleton OIDC déjà livré en M7b. |
| D3 | **GET 404 `rerank_not_configured` → `data: null`** (intercepté côté hook) | Pattern miroir `useOidcConfig` (qui gère 503). Permet au composant d'afficher form vide sans erreur. |
| D4 | **GET 404 `workspace_not_found` → propagation** (geré par le panel parent) | Le panel parent (`WorkspaceDetailPanel`) gère déjà l'absence du workspace via `useWorkspace`. |
| D5 | **Champs dynamiques par provider** (api_key_ref requis pour cohere/voyage, base_url requis pour ollama) | Miroir des contraintes du factory backend (`make_rerank_provider`). Validation côté frontend = bonne UX, validation backend reste autoritative. |
| D6 | Champs non applicables → **disabled** (pas cachés) avec helper text | Transparence : l'admin voit la structure complète du modèle de données et comprend ce qui change selon le provider. |
| D7 | **Suppression sans typing-to-confirm** (AlertDialog standard) | Action réversible (on peut recréer la config en quelques secondes), pas besoin de friction lourde comme `DeleteWorkspaceAlert`. |
| D8 | **Badge "actif" / "non configuré"** dans le header de la section (pas sur le `TabsTrigger`) | Évite de polluer la nav. L'info est visible dès qu'on entre dans l'onglet. |
| D9 | **i18n sous le namespace `workspace`** (section `rerank.*`) | C'est un onglet de `WorkspaceDetailPanel`. Pas de nouveau namespace dédié. |
| D10 | **Pas de StatusIndicator** sur `api_key_ref` | La convention CLAUDE.md vise les variables d'env. Depuis M5, `api_key_ref` est une référence Harpocrate (validée eagerly côté backend au PUT). Cohérent avec `WorkspaceDetailTab` et `WorkspaceModelTab`. |
| D11 | **Affichage `updated_at`** (relative time) en pied de form si configuré | Donne du contexte audit sans alourdir l'IHM. `created_at` non affiché (YAGNI). |
| D12 | **Pas de bouton "tester la config"** | Hors-scope, le PUT effectue déjà la validation eager via Harpocrate. Validation runtime par les recherches MCP réelles. |
| D13 | Aucune modification du contrat backend M8 | M8 est livré et stabilisé. M8b consomme tel quel. |

## 3. Maquettes ASCII

### 3.1 État "non configuré" (GET 404 `rerank_not_configured`)

```
┌── Tab "Rerank" ───────────────────────────────────────────────┐
│                                                                │
│  Reranking (optionnel)                                         │
│  Ajoute une seconde passe de tri sur les hits pgvector. Si     │
│  désactivé, le tri par similarité cosinus seul est utilisé.    │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Provider           [ Sélectionner…           ▾ ]         │  │
│  │ Modèle             [                              ]      │  │
│  │ Base URL (Ollama)  [                              ]      │  │
│  │ Référence clé API  [                              ]      │  │
│  │   Harpocrate                                             │  │
│  │ top_k pré-rerank   [ 50    ]   (1-500)                   │  │
│  │                                                          │  │
│  │                            [ Annuler ]  [ Activer ]      │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ⚠  Si le provider tombe, la recherche échoue (pas de fallback │
│     silencieux). Cohérent avec la philosophie fail-fast.       │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

### 3.2 État "configuré" (GET 200)

```
┌── Tab "Rerank" ───────────────────────────────────────────────┐
│                                                                │
│  Reranking                                       ● actif       │
│  Activé pour ce workspace. Les hits pgvector sont retriés     │
│  par le modèle sélectionné avant retour MCP.                  │
│                                                                │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │ Provider           [ Cohere                    ▾ ]       │  │
│  │ Modèle             [ rerank-english-v3.0           ]     │  │
│  │ Base URL (Ollama)  [ — non applicable —            ]     │  │
│  │ Référence clé API  [ cohere_rerank_key             ]     │  │
│  │   Harpocrate                                             │  │
│  │ top_k pré-rerank   [ 50    ]   (1-500)                   │  │
│  │                                                          │  │
│  │  Dernière modification : il y a 2 h                      │  │
│  │                                                          │  │
│  │  [ Supprimer la config ]   [ Annuler ]  [ Enregistrer ]  │  │
│  └──────────────────────────────────────────────────────────┘  │
│                                                                │
│  ⚠  Si le provider tombe, la recherche échoue (fail-fast).    │
│                                                                │
└───────────────────────────────────────────────────────────────┘
```

### 3.3 AlertDialog de suppression

```
┌── AlertDialog ────────────────────────────────────────┐
│  Désactiver le reranking ?                            │
│                                                       │
│  La configuration rerank de ce workspace sera         │
│  supprimée. Les prochaines recherches utiliseront     │
│  uniquement la similarité cosinus pgvector.           │
│                                                       │
│  Cette action est réversible (recréer la config).     │
│                                                       │
│            [ Annuler ]   [ Désactiver ]               │
└──────────────────────────────────────────────────────┘
```

## 4. Modèle de données frontend

### 4.1 `frontend/src/lib/rerank.types.ts`

Miroirs des schémas Pydantic backend (`backend/src/rag/schemas/admin.py`).

```typescript
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

### 4.2 `frontend/src/lib/rerank.ts`

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

> **Note** : `api.put` n'existe pas aujourd'hui dans `frontend/src/lib/api.ts` (seuls `get/post/patch/delete` sont exposés — vérifié). T1 doit ajouter la méthode `put` en parallèle de `post`, même structure.

### 4.3 `frontend/src/hooks/useRerank.ts`

```typescript
export function useRerankConfig(name: string) {
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
  });
}

export function useUpsertRerankConfig(name: string) { /* invalidate rerank key */ }
export function useDeleteRerankConfig(name: string) { /* invalidate rerank key */ }
```

**Note implémentation** : `ApiError` actuel (`frontend/src/lib/api.ts`) expose le body parsé via `err.body: unknown` (pas de champ `detail` direct). Le hook doit donc tester `(err.body as { detail?: string })?.detail === "rerank_not_configured"`. T1 introduit un helper `isErrorBodyWithDetail(body, expected): boolean` dans `lib/api.ts` pour ne pas dupliquer le narrowing à chaque site d'appel — il pourra resservir pour d'autres erreurs typées FastAPI (cf. usage existant dans `useOidcConfig` qui filtre seulement sur le status 503).

## 5. Validation Zod (conditionnelle par provider)

```typescript
const schema = z
  .object({
    provider: z.enum(["cohere", "voyage", "ollama"]),
    model: z.string().min(1, "required"),
    api_key_ref: z
      .string()
      .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only")
      .nullable(),
    base_url: z.string().url("invalid_url").nullable(),
    top_k_pre_rerank: z
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
```

Les champs non applicables passent en `disabled` côté JSX dès le changement de provider :

```tsx
const provider = form.watch("provider");
const apiKeyApplicable = provider === "cohere" || provider === "voyage";
const baseUrlApplicable = provider === "ollama";
```

## 6. Composants

### 6.1 `WorkspaceRerankTab.tsx`

Responsabilités :
- Charger la config via `useRerankConfig(name)`.
- Initialiser le form (default values) selon `data` ou un `EMPTY` template.
- Synchroniser le form quand `data` arrive (`useEffect` avec `form.reset`).
- Rendre le form avec champs dynamiques par provider.
- Bouton `Enregistrer` (submit, PUT) — disabled si `!isDirty` ou pending.
- Bouton `Annuler` — `form.reset(data ?? EMPTY)`, disabled si `!isDirty`.
- Bouton `Supprimer la config` — visible seulement si `data !== null`, ouvre `DeleteRerankAlert`.
- Badge en header `● actif` / `(optionnel)` selon `data !== null`.
- Footer "Dernière modification : il y a X" si `data !== null`, utilise le helper `relativeTimeRaw` du `WorkspaceDetailTab` (à factoriser dans `lib/utils.ts` si possible, sinon dupliquer pour M8b et factoriser plus tard).

Signature :
```typescript
interface Props {
  workspace: Workspace;
  enabled: boolean; // pour activer/désactiver le useQuery selon onglet actif
}
```

> Le pattern `enabled` suit `WorkspaceSourcesTab` / `WorkspaceJobsTab` (cf. `WorkspaceDetailPanel.tsx:62-66`).

### 6.2 `DeleteRerankAlert.tsx`

`AlertDialog` shadcn standard, paramétré par `name`. Bouton de confirmation lance `useDeleteRerankConfig(name)`. Toast succès/erreur. Pattern parallèle à `DeleteSourceAlert.tsx`.

### 6.3 Modifications `WorkspaceDetailPanel.tsx`

Ajout d'un `<TabsTrigger value="rerank">` + `<TabsContent value="rerank">` avec `<WorkspaceRerankTab workspace={ws} enabled={activeTab === "rerank"} />`.

## 7. i18n

Ajouts à `frontend/src/i18n/{fr,en}/workspace.json` sous une nouvelle clé `rerank` :

```json
{
  "tabs": {
    "...": "...",
    "rerank": "Rerank"
  },
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
      "model": "Modèle",
      "baseUrl": "Base URL (Ollama)",
      "baseUrlNotApplicable": "— non applicable —",
      "apiKeyRef": "Référence clé API Harpocrate",
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
  }
}
```

Versions EN équivalentes dans `en/workspace.json`. Le bouton submit utilise `activate` si `data === null`, sinon `save`.

## 8. Tests Vitest

Fichier `frontend/src/pages/workspace/__tests__/WorkspaceRerankTab.test.tsx`, basé sur `testUtils.tsx` existant (cf. `WorkspaceModelTab.test.tsx` pour le pattern de mock).

| Cas | Couverture |
|---|---|
| `renders empty state when GET 404 rerank_not_configured` | Form vide, bouton "Activer", pas de bouton "Supprimer", pas de badge "actif". |
| `renders configured state when GET 200` | Form pré-rempli, bouton "Enregistrer", bouton "Supprimer" visible, badge "actif". |
| `disables api_key_ref when provider is ollama` | Switch via select → field disabled + helper text. |
| `disables base_url when provider is cohere` | Idem inverse. |
| `submits PUT with form values on save` | Mock PUT, click "Enregistrer", body contient les valeurs. |
| `shows Zod error when cohere selected without api_key_ref` | Submit → erreur visible. |
| `shows Zod error when ollama selected without base_url` | Submit → erreur visible. |
| `opens AlertDialog on delete click, confirms DELETE` | Click "Supprimer la config" → dialog → confirm → mock DELETE appelé → invalidate. |
| `shows last modified relative time when configured` | Mock `updated_at` ISO → texte attendu. |

Couverture cible : ≥ 90% sur `WorkspaceRerankTab.tsx` et `DeleteRerankAlert.tsx`.

## 9. Plan d'attaque (taille indicative)

~0.5 jour frontend, 7 tâches.

| # | Tâche | Périmètre |
|---|---|---|
| T1 | Types TS + API client + hooks rerank | `lib/rerank.types.ts`, `lib/rerank.ts`, `hooks/useRerank.ts`. Ajout `api.put` à `lib/api.ts` (manquant aujourd'hui). Ajout helper `isErrorBodyWithDetail(body, expected)` pour le narrowing du `detail` FastAPI. |
| T2 | `WorkspaceRerankTab.tsx` form + validation Zod | Composant principal avec champs dynamiques + form. Pas encore branché dans le panel. |
| T3 | `DeleteRerankAlert.tsx` | AlertDialog réutilisant `useDeleteRerankConfig`. |
| T4 | Branchement onglet dans `WorkspaceDetailPanel` | Ajout `TabsTrigger` + `TabsContent`. |
| T5 | i18n FR + EN | Ajouts dans `workspace.json` (2 langues). |
| T6 | Tests Vitest `WorkspaceRerankTab.test.tsx` | 9 cas listés en §8. |
| T7 | Lint + audit strings (vérifier qu'aucun label codé en dur ne traîne) + smoke manuel | `npm run lint`, `npx tsc --noEmit`, démarrer le dev server, ouvrir un workspace, naviguer dans tous les états (vide, configuré, switch provider, suppression). |

## 10. Hors-scope explicite

- **Bouton "tester la config"** (validation runtime via un appel réel au provider) → V2 si besoin.
- **Badge/indicateur sur le `TabsTrigger`** lui-même → YAGNI, le badge dans l'onglet suffit.
- **Page admin globale "Rerank configs across all workspaces"** → non, design singleton-by-workspace.
- **Historique des modifications** (`created_at` détaillé, audit log) → YAGNI.
- **Préview de l'effet du rerank** sur une requête test → V2 si besoin (nécessite endpoint backend dédié).
- **Métriques par config rerank** (latence p99, taux d'erreur) → couvert par Grafana Loki, pas dans cette IHM.
- **Variables d'env `COHERE_RERANK_KEY` / `VOYAGE_RERANK_KEY` exposées comme `StatusIndicator`** → non, le pattern post-M5 utilise des refs Harpocrate, pas des variables d'env.
