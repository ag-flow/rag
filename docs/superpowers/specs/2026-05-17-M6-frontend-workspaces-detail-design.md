# M6 — Page Workspaces détail + sources git (frontend)

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/02-api-admin.md` (workspaces CRUD + sources + jobs).
> **Prérequis** : M5b (frontend bootstrap), M5cd-front (Coffres Harpocrate — pattern à reprendre), M5e (endpoint GET apikey idempotent), M5f (préfixe `/api/admin` partout).

## 1. Contexte et motivation

La page Workspaces actuelle (M5b) est une **table liste plate** sans détail :

```
WorkspacesPage.tsx (M5b)
├── table : name | indexer | sources | docs | last_indexed
└── dialog Create + dropdown ⋯ par ligne (rotate/reindex/delete)
```

On ne peut **pas** :
- voir la config détaillée d'un workspace (api_key_ref, base pgvector, dimension)
- gérer les **sources git** attachées (le backend `POST/DELETE /workspaces/{name}/sources` existe depuis M3 mais n'a aucune UI)
- consulter l'historique des **jobs d'indexation** (`GET /workspaces/{name}/jobs` existe également)
- **révéler** l'api_key courante (l'endpoint M5e `GET /apikey` est inutilisé côté UI)

Le pattern de la page **Coffres Harpocrate** livré en M5cd-front (master-detail + 3 onglets + dialogs) a fait ses preuves et sera **répliqué exactement** pour les workspaces, avec adaptation au modèle métier.

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | **Paradigme master-detail** (liste 240px + détail avec onglets) | Cohérence avec page Coffres Harpocrate, meilleur scan latéral, sélection synchronisée URL |
| D2 | **4 onglets** : Détail / Sources git / Jobs / Modèle | Choix utilisateur (option 3) — couverture complète des données backend |
| D3 | **Sources git en accordion** (table compacte + expand inline) | Tous les champs visibles sans dialog, click pour étendre |
| D4 | **Édition limitée à `indexer.api_key_ref`** | Le backend `patch_workspace` (services/workspaces.py:212) ne supporte que ce champ. Tout le reste en lecture seule. PATCH élargi reporté à un jalon backend ultérieur |
| D5 | **Header workspace = sticky** avec Reindex + menu ⋯ (Reveal / Rotate / Delete) | Pattern Coffres Harpocrate (VaultHeader) |
| D6 | **Sélection synchronisée URL** : `?ws=<name>` | Identique à `?vault=<id>` de Harpocrate. Permet bookmark + reload |
| D7 | **Lazy loading** des onglets Sources / Jobs (React Query `enabled`) | Pas de fetch inutile avant ouverture de l'onglet |
| D8 | **Onglet Modèle = lecture seule** avec note explicite « immutable, changer nécessite réindexation » | Cohérent avec le backend et la spec 02-api-admin |
| D9 | **Pas de WorkspacesPage M5b conservée** — la page actuelle est remplacée par le master-detail | Évite la confusion deux UIs pour le même domaine |

## 3. Architecture frontend

### 3.1 Composants à créer (sous `frontend/src/pages/workspace/`)

```
frontend/src/pages/
├── WorkspacesPage.tsx                       [REWRITE] container master-detail
└── workspace/
    ├── WorkspacesList.tsx                   [NEW] panneau gauche (liste 240px)
    ├── WorkspacesEmptyState.tsx             [NEW] état vide (premier workspace)
    ├── WorkspaceDetailPanel.tsx             [NEW] container droite (header + tabs)
    ├── WorkspaceHeader.tsx                  [NEW] sticky : nom + Reindex + menu ⋯
    ├── WorkspaceDetailTab.tsx               [NEW] onglet Détail
    ├── WorkspaceSourcesTab.tsx              [NEW] onglet Sources git (accordion)
    ├── WorkspaceJobsTab.tsx                 [NEW] onglet Jobs (historique)
    ├── WorkspaceModelTab.tsx                [NEW] onglet Modèle (read-only)
    ├── RevealApiKeyDialog.tsx               [NEW] dialog reveal masqué
    ├── RotateApiKeyDialog.tsx               [NEW] dialog rotate + display nouvelle clé
    ├── ReindexConfirmDialog.tsx             [NEW] confirm reindex (alert si vecteurs existent)
    ├── AddSourceDialog.tsx                  [NEW] dialog ajout source git
    ├── EditSourceDialog.tsx                 [NEW] dialog édition source git
    ├── DeleteWorkspaceAlert.tsx             [REWRITE] alert avec input nom-confirmation
    └── DeleteSourceAlert.tsx                [NEW] alert delete source
```

### 3.2 Composants existants à supprimer ou refactorer

| Fichier | Action | Raison |
|---|---|---|
| `frontend/src/pages/WorkspacesPage.tsx` | **Réécrit** | Remplace la table M5b par le master-detail |
| `frontend/src/pages/WorkspaceCreateDialog.tsx` | **Déplacé** vers `workspace/CreateWorkspaceDialog.tsx` | Ranger sous le namespace |
| `frontend/src/pages/WorkspaceActions.tsx` | **Supprimé** | Le dropdown ligne disparaît, ses actions migrent vers WorkspaceHeader (menu ⋯) |
| `frontend/src/pages/WorkspaceDeleteAlert.tsx` | **Réécrit** vers `workspace/DeleteWorkspaceAlert.tsx` | Ajouter input nom-confirmation cohérent avec RetireVaultDialog |

### 3.3 Hooks React Query (`frontend/src/hooks/useWorkspaces.ts` étendu)

Hooks existants à conserver (M5b) : `useWorkspaces`, `useCreateWorkspace`, `useDeleteWorkspace`, `useRotateApiKey`, `useReindex`.

Hooks à ajouter :

```typescript
// Détail
useWorkspace(name: string): UseQueryResult<Workspace>;             // GET /workspaces/{name}
useUpdateApiKeyRef(): UseMutationResult<...>;                      // PATCH /workspaces/{name}
useRevealApiKey(name: string): UseMutationResult<...>;             // GET /workspaces/{name}/apikey (lazy, on-click)

// Sources git (lazy : enabled = activeTab === 'sources')
useWorkspaceSources(name: string, enabled: boolean): UseQueryResult<Source[]>;  // injecté par useWorkspace.data.sources si exposé, sinon endpoint dédié
useAddSource(name: string): UseMutationResult<...>;                // POST /workspaces/{name}/sources
useDeleteSource(name: string): UseMutationResult<...>;             // DELETE /workspaces/{name}/sources/{source_id}
// Pas de `useUpdateSource` — l'édition d'une source n'est pas supportée backend (cf. § 9).

// Jobs (lazy)
useWorkspaceJobs(name: string, enabled: boolean): UseQueryResult<Job[]>;  // GET /workspaces/{name}/jobs
```

Les hooks `useWorkspaceSources` et `useWorkspaceJobs` utilisent `enabled` pour lazy-load — pas de fetch tant que l'onglet correspondant n'est pas ouvert.

### 3.4 Types TS (`frontend/src/lib/workspaces.types.ts`)

Types miroirs des schemas Pydantic backend :

- `Workspace` (déjà existant M5b)
- `WorkspaceCreate` / `WorkspaceCreateResponse` (existants)
- `WorkspacePatchRequest` (déjà : `{ indexer: { api_key_ref } }`)
- `Source` ← miroir `SourceResponse` (id, type, config, last_indexed_at, created_at)
- `SourceConfig` ← `{ url, branch, auth_ref?, include[], exclude[] }`
- `SourceCreateRequest` ← `{ type: "git", config: SourceConfig }`
- `Job` ← miroir `JobResponse` (id, triggered_by, status, files_changed, files_skipped, error_message, started_at, finished_at, duration_ms)
- `ApiKeyRotateResponse` ← `{ api_key: string }` (utilisé aussi par GET /apikey en M5e)

## 4. Endpoints backend consommés

Tous sous `/api/admin` (préfixe livré en M5f).

| Méthode | Path | Hook | Contexte d'appel |
|---|---|---|---|
| GET | `/api/admin/workspaces` | `useWorkspaces` | Page mount, liste gauche |
| GET | `/api/admin/workspaces/{name}` | `useWorkspace` | Sélection workspace |
| POST | `/api/admin/workspaces` | `useCreateWorkspace` | Dialog Create |
| PATCH | `/api/admin/workspaces/{name}` | `useUpdateApiKeyRef` | Save api_key_ref onglet Détail |
| DELETE | `/api/admin/workspaces/{name}` | `useDeleteWorkspace` | Menu ⋯ → Delete |
| POST | `/api/admin/workspaces/{name}/rotate-apikey` | `useRotateApiKey` | Dialog Rotate |
| GET | `/api/admin/workspaces/{name}/apikey` | `useRevealApiKey` | Dialog Reveal (M5e) |
| POST | `/api/admin/workspaces/{name}/sources` | `useAddSource` | AddSourceDialog |
| DELETE | `/api/admin/workspaces/{name}/sources/{id}` | `useDeleteSource` | DeleteSourceAlert |
| POST | `/api/admin/workspaces/{name}/reindex` | `useReindex` | ReindexConfirmDialog |
| GET | `/api/admin/workspaces/{name}/jobs` | `useWorkspaceJobs` | Onglet Jobs (lazy) |

**Endpoint manquant pour Sources** : la mutation **Edit source** (`PATCH /workspaces/{name}/sources/{id}`) n'existe **pas** côté backend en M3. Cf. § 9 Hors-scope — l'onglet Sources expose **Add + Delete uniquement** dans M6 ; l'édition d'une source existante passe par delete+add.

## 5. Layout et UX

### 5.1 Master-detail

```
┌─────────────────────────────────────────────────────────┐
│  240px                  max 760px                       │
│  ┌─────────────────┐    ┌──────────────────────────┐   │
│  │ Workspaces (3)  │    │ harpocrate    [↻ Reindex]│   │
│  │ + Nouveau       │    │   créé il y a 8 j     ⋯  │   │
│  │ ▸ harpocrate    │    │ ──────────────────────── │   │
│  │   rag-corpus    │    │ Détail │ Sources │ Jobs │   │
│  │   internal-docs │    │ │ Modèle                 │   │
│  │                 │    │                          │   │
│  │                 │    │ <contenu onglet actif>   │   │
│  └─────────────────┘    └──────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

- Liste 240px à gauche : nom + résumé (indexer · docs count).
- Panneau détail max 760px à droite, scroll vertical.
- Sélection synchronisée à `?ws=<name>` (URLSearchParams).
- Auto-sélection du premier workspace au load (si `?ws=` absent).

### 5.2 Header workspace (sticky)

```
┌──────────────────────────────────────────────────────────┐
│ harpocrate                       [↻ Reindex]     ⋯      │
│ créé il y a 8 j                                          │
└──────────────────────────────────────────────────────────┘
```

- Nom (h2) + date création (subtitle).
- Bouton **Reindex** → ouvre `ReindexConfirmDialog` (variante alert si la response API confirme `requires_confirm=true`).
- Menu **⋯** :
  - **Révéler la clé API** → RevealApiKeyDialog
  - **Régénérer la clé API** → RotateApiKeyDialog
  - **Supprimer le workspace** → DeleteWorkspaceAlert

### 5.3 Onglet Détail

3 sections verticales :

1. **Statistiques** (read-only) : sources / documents / dernière sync (relative time).
2. **API key workspace** : champ masqué `••••••••` + boutons **Révéler** et **Régénérer** (raccourcis du menu ⋯).
3. **Référence Harpocrate (modifiable)** : input `api_key_ref` + bouton **Save** (enabled si dirty). Validation Zod : non-vide, chars alphanumériques + `_`.
4. **Identifiants (read-only)** : `name`, `id`, base pgvector (`rag_<name>`).

### 5.4 Onglet Sources git (accordion)

```
┌─────────────────────────────────────────────────┐
│ Sources git (3)                  [+ Ajouter]   │
├─────────────────────────────────────────────────┤
│ ▾ github.com/.../harpocrate · main · 12 min ⋯ │
│    auth: github_token                          │
│    include: **/*.md                            │
│    exclude: —                                  │
│    prochaine sync: dans 4 min                  │
├─────────────────────────────────────────────────┤
│ ▸ github.com/.../docs · main · 2 h           ⋯│
├─────────────────────────────────────────────────┤
│ ▸ azuredevops/.../specs · develop · jamais   ⋯│
└─────────────────────────────────────────────────┘
```

- Ligne compacte : URL · branch · last_indexed_at (relative).
- Click ligne → expand inline (auth_ref · include · exclude · next_sync_at).
- Menu ⋯ : **Supprimer** (DeleteSourceAlert). Pas d'édition en M6 (cf. § 9).
- État vide : illustration + bouton "+ Ajouter votre première source".

### 5.5 Onglet Jobs

```
┌─────────────────────────────────────────────────┐
│ Jobs (12 derniers)                              │
├─────────────────────────────────────────────────┤
│ ● done · webhook · 3 ch / 58 sk · 1.2s · 12min │
│ ● done · schedule · 0 ch / 61 sk · 0.4s · 4h   │
│ ● error · manual · — · — · 6h                  │
│   ▸ error_message: connection refused          │
└─────────────────────────────────────────────────┘
```

- Tableau des 50 dernières lignes (limite côté backend).
- Colonnes : status (badge coloré : `done` vert, `error` rouge, `running`/`pending` bleu) · triggered_by · files_changed/files_skipped · duration_ms · started_at (relative).
- Click ligne erreur → expand le `error_message` inline.
- Pas de pagination dans M6 — limite 50 récents, ordre `started_at DESC`. Au-delà : message « historique limité aux 50 derniers » (à dimensionner selon backend).

### 5.6 Onglet Modèle (read-only)

Liste de paires clé/valeur :

- `provider` · `model` · `dimension` · `base_url` (si présent) · `api_key_ref`

Note encadrée : **« Le modèle est immutable. Changer provider ou model invaliderait toutes les dimensions vecteurs et nécessiterait une réindexation complète, non supportée dans cette version. »**

## 6. Dialogs et alerts (specs comportementales)

### 6.1 `CreateWorkspaceDialog` (existant M5b, à conserver)

Pas de modification, juste déplacement dans `workspace/`.

### 6.2 `RevealApiKeyDialog`

- Bouton ouverture : « Révéler la clé API » (menu ⋯ ou bouton direct dans onglet Détail).
- Étape 1 : warning rouge « Affiche la clé en clair. Continuer ? » + bouton Confirmer.
- Étape 2 : appel `useRevealApiKey()` → display la clé en `<code>` avec bouton Copier. Auto-masquage après 30s.

### 6.3 `RotateApiKeyDialog`

- Warning rouge « Cette action invalide immédiatement la clé actuelle. Les agents existants devront être reconfigurés. »
- Input « Tape le nom du workspace pour confirmer » (anti-erreur, cohérent avec RetireVaultDialog Harpocrate).
- Confirm → appel `useRotateApiKey()` → display la nouvelle clé avec bouton Copier (one-time view, masqué au fermer).

### 6.4 `ReindexConfirmDialog`

- Confirmation simple (oui/non) avant déclenchement → POST `/reindex?confirm=true` (le query-param `confirm=true` est imposé par le contrat backend pour ce endpoint).
- Warning text : « Toutes les sources du workspace seront re-synchronisées. Les documents non modifiés sont skip (déduplication SHA-256). »
- Toast de succès « Réindexation déclenchée » + invalidate `useWorkspaceJobs`.

Note : un PATCH workspace qui changerait `provider`/`model` renverrait `409 indexer_change_requires_reindex` (cf. spec 02-api-admin). Ce cas est **hors-scope M6** puisque seul `api_key_ref` est patchable. Si plus tard ce PATCH s'élargit, on consommera ce 409 dans le composant qui appelle `useUpdateApiKeyRef` — pas ici.

### 6.5 `AddSourceDialog`

Formulaire Zod :

```typescript
{
  url: string (URL valide),
  branch: string (default "main"),
  auth_ref: string | null (clé logique Harpocrate, optionnelle),
  include: string[] (globs, comma-separated input → array),
  exclude: string[] (idem),
}
```

Submit → POST `/sources` avec payload `{ type: "git", config: {...} }`. Toast succès, invalidate `useWorkspaceSources`.

### 6.6 `DeleteWorkspaceAlert`

shadcn AlertDialog :

- Warning rouge « Supprime le workspace + sa base pgvector + tous ses documents indexés. Irréversible. »
- Input « Tape `<workspace_name>` pour confirmer » — bouton Confirm disabled tant que mismatch.
- Confirm → DELETE workspaces, toast, redirect liste vide ou auto-sélection suivant.

### 6.7 `DeleteSourceAlert`

shadcn AlertDialog :

- Warning : « Supprime la source. Les documents déjà indexés restent. »
- Confirm direct (pas d'input — la source est identifiée par son ID, moins critique).

## 7. i18n

Namespace `workspace` dans `frontend/src/i18n/`. Tous les labels affichés passent par `useTranslation("workspace")`. Aucune string brute.

Sections de clés à prévoir :

- `workspace.list.*` (titre, empty state, créer)
- `workspace.header.*` (reindex, menu items)
- `workspace.detail.tab.*` (titres onglets, sections, labels)
- `workspace.sources.*` (table, add, delete, accordion)
- `workspace.jobs.*` (status badges, colonnes)
- `workspace.model.*` (note immutable, labels)
- `workspace.dialog.reveal.*` / `rotate.*` / `reindex.*` / `addSource.*` / `delete.*`
- `workspace.errors.*` (mapping codes backend → libellés humains)

Suit le pattern `harpocrate.*` livré en M5cd-front.

## 8. Tests

Stratégie alignée sur M5cd-front (Vitest + React Testing Library).

### 8.1 Tests unit Vitest

| Fichier | Couverture |
|---|---|
| `WorkspacesPage.test.tsx` | Render liste + sélection URL + auto-sélection premier item |
| `WorkspacesList.test.tsx` | Render items + bouton créer + état vide |
| `WorkspaceDetailTab.test.tsx` | Render sections + edit api_key_ref + Save désactivé si non-dirty |
| `WorkspaceSourcesTab.test.tsx` | Accordion expand/collapse + delete confirm + add via dialog |
| `WorkspaceJobsTab.test.tsx` | Badge status + expand error_message |
| `RevealApiKeyDialog.test.tsx` | Étape warning → confirm → display clé + auto-mask 30s |
| `RotateApiKeyDialog.test.tsx` | Input confirm name + rotate + display nouvelle clé |
| `AddSourceDialog.test.tsx` | Validation Zod + submit + reset |

### 8.2 Audit i18n

Comme M5cd-front : script qui scanne les composants pour détecter des chaînes hardcoded en dehors de `t()`. Échoue si une string brute apparaît dans le JSX.

## 9. Hors-scope (explicite)

| Élément | Raison |
|---|---|
| **Édition d'une source existante** (PATCH) | Endpoint backend absent. Workaround : delete + add (acceptable en M6) |
| **Édition de `name`, `provider`, `model`, `base_url`** | Backend `patch_workspace` limité à `api_key_ref`. Reporté à un jalon backend ultérieur si besoin |
| **Pagination Jobs au-delà de 50** | Limite côté backend acceptée pour M6. Si l'historique devient un besoin, jalon dédié |
| **Force-sync d'une seule source** | Endpoint backend absent. Reindex actuel = global au workspace |
| **Édition des `include`/`exclude` post-création** | Couplé à l'édition de source (cf. ligne 1) |
| **Vue détaillée d'un job individuel (logs, traces)** | Backend ne le supporte pas |
| **Streaming jobs en cours** (websocket / SSE) | Pas dans M6 — polling React Query suffit |

## 10. Risques et mitigations

| Risque | Mitigation |
|---|---|
| Accord disability ↔ Save bouton incohérents | Tests RTL sur chaque combinaison dirty/loading/error |
| 503 si DEK absent au reveal-apikey | Toast d'erreur clair « Service indisponible — RAG_API_KEY_DEK manquant côté serveur » |
| Workspace avec **0 indexer_configs** orphelin | Le détail affiche un placeholder « Aucun indexer configuré » + lien vers la doc. Cas pratique : test seul utile, pas une feature à exposer |
| Réindexation longue (> 30s) | Toast « Réindexation déclenchée » non bloquant + polling `useWorkspaceJobs` toutes les 5s pendant 5 min après déclenchement |
| Cache React Query stale après rotate apikey | `onSuccess` → invalidate `useWorkspace(name)` et `useWorkspaces` |

## 11. Plan d'attaque proposé

Le plan TDD détaillé sera écrit avec la skill `writing-plans`. Vision haut-niveau :

1. **T1** — Types TS + API client (workspaces.types.ts + workspaces.ts étendu)
2. **T2** — Hooks React Query étendus (useWorkspace, useRevealApiKey, useWorkspaceSources, useWorkspaceJobs, mutations sources)
3. **T3** — Refactor `WorkspacesPage.tsx` master-detail + `WorkspacesList` + auto-sélection URL
4. **T4** — `WorkspaceDetailPanel` + `WorkspaceHeader` + tabs structure
5. **T5** — `WorkspaceDetailTab` (édition api_key_ref + sections read-only)
6. **T6** — `WorkspaceSourcesTab` (accordion + AddSourceDialog + DeleteSourceAlert)
7. **T7** — `WorkspaceJobsTab` (table historique + expand error)
8. **T8** — `WorkspaceModelTab` (read-only + note immutable)
9. **T9** — Dialogs API key : RevealApiKeyDialog + RotateApiKeyDialog
10. **T10** — `ReindexConfirmDialog` + `DeleteWorkspaceAlert` réécrite + menu ⋯ header
11. **T11** — i18n complet FR + EN + audit strings + tests Vitest

Estimation : 11 tâches, ~2 à 3 jours frontend.

## 12. Cohérence avec les autres pages

Le pattern UX/code de M5cd-front (Coffres Harpocrate) est rejoué à l'identique. Tout futur module admin (jobs globaux, modèles, oidc) bénéficiera du même cadre.
