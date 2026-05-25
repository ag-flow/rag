# M7a — Page Modèles admin (frontend)

> **Statut** : design validé pour implémentation.
> **Backend** : déjà livré (M2) — `/api/admin/models` GET/POST/DELETE.
> **Prérequis** : M5b (frontend bootstrap), M5f (préfixe `/api/admin`).

## 1. Contexte

Le backend expose un registre `model_dimensions` (table BDD, migration 005) qui répertorie les couples (provider, model, dimension) supportés pour la création de workspaces. Trois providers réellement supportés côté indexer : **openai**, **voyage**, **ollama** (cf. `backend/src/rag/indexer/providers/factory.py`).

Actuellement, ce catalogue ne peut être édité **que via SQL direct** ou les endpoints HTTP sans UI. M7a livre une page d'administration `/settings/models` pour gérer ce catalogue à la main.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Layout **accordion par provider** | Choix utilisateur. Sections repliables triées alphabétiquement par provider. Plus visuel quand la liste grossit |
| D2 | Provider en **Select pré-défini + "autre"** | Choix utilisateur. Liste contrainte à `openai` / `voyage` / `ollama` (réellement supportés), + option "autre" qui ouvre un input libre (anticipe extension) |
| D3 | Pas d'édition (PATCH absent) | La clé primaire `(provider, model)` est immutable côté backend. Modification = delete + add |
| D4 | Delete alert simple (sans input nom-confirmation) | Action peu critique : un modèle supprimé n'affecte pas les workspaces existants, juste la création de nouveaux |

## 3. Architecture

### 3.1 Fichiers à créer

```
frontend/src/lib/models.types.ts          → type ModelEntry
frontend/src/lib/models.ts                → modelsApi (3 méthodes)
frontend/src/hooks/useModels.ts           → 1 query + 2 mutations
frontend/src/pages/ModelsPage.tsx         → container avec accordion par provider
frontend/src/pages/models/AddModelDialog.tsx
frontend/src/pages/models/DeleteModelAlert.tsx
frontend/src/i18n/fr/models.json
frontend/src/i18n/en/models.json
```

### 3.2 Fichiers à modifier

```
frontend/src/routes.tsx                   → +Route /settings/models
frontend/src/components/Sidebar.tsx       → +item Configuration → Modèles
frontend/src/i18n/i18n.ts                 → enregistrer namespace "models"
frontend/src/i18n/fr/nav.json             → +clé settings.models
frontend/src/i18n/en/nav.json             → idem
```

### 3.3 Types TS

```typescript
// lib/models.types.ts
export type ModelEntry = {
  provider: string;
  model: string;
  dimension: number;
  created_at: string;
};

export type ModelCreateRequest = {
  provider: string;
  model: string;
  dimension: number;
};
```

### 3.4 API client (`lib/models.ts`)

```typescript
const BASE = "/api/admin/models";

export const modelsApi = {
  list: () => api.get<ModelEntry[]>(BASE),
  create: (payload: ModelCreateRequest) => api.post<ModelEntry>(BASE, payload),
  delete: (provider: string, model: string) =>
    api.delete<void>(`${BASE}/${provider}/${model}`),
};
```

### 3.5 Hooks (`hooks/useModels.ts`)

- `useModels()` — query `["models"]`
- `useCreateModel()` — mutation, onSuccess invalide `["models"]`
- `useDeleteModel()` — mutation `(provider, model)`, onSuccess invalide `["models"]`

## 4. Layout UI

### 4.1 `ModelsPage.tsx`

```
┌──────────────────────────────────────────────────────────┐
│  Modèles d'embedding (7)                  [+ Ajouter]   │
├──────────────────────────────────────────────────────────┤
│  ▾ ollama (3)                                            │
│    nomic-embed-text     · dim 768   · il y a 5 j  ⋯     │
│    mxbai-embed-large    · dim 1024  · il y a 2 j  ⋯     │
│    qwen2.5-coder:14b    · dim 4096  · il y a 8 j  ⋯     │
├──────────────────────────────────────────────────────────┤
│  ▸ openai (2)                                            │
├──────────────────────────────────────────────────────────┤
│  ▸ voyage (2)                                            │
└──────────────────────────────────────────────────────────┘
```

- Sections accordion shadcn (`@/components/ui/accordion`), repliables. Sections ouvertes par défaut.
- Header section : provider + `({count})`.
- Lignes : `model · dim {N} · {relative}` + menu ⋯ → Supprimer.
- Tri : providers alphabétiques, models alphabétiques dans chaque section.
- État vide global : "Aucun modèle enregistré. Ajoutez-en un pour commencer." + bouton.

### 4.2 `AddModelDialog.tsx`

Form react-hook-form + Zod :

```typescript
const schema = z.object({
  providerSelect: z.enum(["openai", "voyage", "ollama", "autre"]),
  providerOther: z.string().optional(),
  model: z.string().min(1),
  dimension: z.coerce.number().int().positive(),
}).refine(
  (v) => v.providerSelect !== "autre" || (v.providerOther && v.providerOther.length > 0),
  { message: "provider_other_required", path: ["providerOther"] },
);
```

- **Provider** : `<Select>` avec 4 options (openai/voyage/ollama/autre). Si "autre" → champ Input texte libre apparaît en dessous.
- **Model** : input texte.
- **Dimension** : input number positif.
- Submit → POST → toast succès + invalidate + reset.
- 409 (conflict provider/model existant) : toast erreur "Ce couple existe déjà".

### 4.3 `DeleteModelAlert.tsx`

AlertDialog shadcn :
- Titre : "Supprimer le modèle".
- Description : "Supprime `{provider}/{model}` du catalogue. Les workspaces existants qui utilisent ce modèle continuent de fonctionner — on ne pourra simplement plus en créer de nouveaux avec."
- Boutons : Annuler / Supprimer (rouge).

### 4.4 Navigation

- Sidebar : sous le bloc Configuration existant (qui contient déjà "Coffres Harpocrate"), ajouter **Modèles** avec icône `Boxes` ou `Sparkles` de lucide-react.
- Route : `/settings/models`.
- Lien sidebar actif si URL match.

## 5. Tests Vitest (3 fichiers)

| Fichier | Couverture |
|---|---|
| `ModelsPage.test.tsx` | Render accordion + groupement par provider + état vide |
| `AddModelDialog.test.tsx` | Select provider + champ "autre" conditionnel + validation Zod + submit |
| `DeleteModelAlert.test.tsx` | Confirm → mutation appelée |

Pattern : `frontend/src/pages/workspace/__tests__/*.test.tsx` (M6).

## 6. i18n (namespace `models`)

Clés :

- `models.title` — "Modèles d'embedding"
- `models.count` — "{{count}} modèles"
- `models.add` — "Ajouter"
- `models.empty` — "Aucun modèle enregistré."
- `models.section.count` — "({{count}})"
- `models.row.dim` — "dim {{dimension}}"
- `models.row.created` — "il y a {{when}}"
- `models.row.delete` — "Supprimer"
- `models.dialog.add.*` — title, fields (provider, providerOther, model, dimension), submit, errors
- `models.dialog.delete.*` — title, warning, confirm
- `models.errors.duplicate` — "Ce couple provider/model existe déjà."

## 7. Hors-scope

- Édition d'un modèle (PATCH absent côté backend, par design).
- Validation de la cohérence dimension ↔ provider (ex: openai/text-embedding-3-small = 1536) — laissée à l'admin.
- Détection automatique de la dimension via appel API au provider — pas dans M7a.
- Liste suggestive des models par provider — pas dans M7a, l'admin connaît son catalogue.

## 8. Plan d'attaque

Le plan TDD détaillé sera écrit avec `writing-plans`. Vision haut-niveau :

1. **T1** — Types TS + API client (`models.types.ts`, `models.ts`)
2. **T2** — Hooks React Query (`useModels.ts`)
3. **T3** — Sidebar +item Modèles + route + `ModelsPage` squelette
4. **T4** — `ModelsPage` accordion par provider + état vide
5. **T5** — `AddModelDialog` + `DeleteModelAlert`
6. **T6** — i18n complet FR+EN + 3 tests Vitest + audit strings

Estimation : 6 tâches, ~demi-journée.
