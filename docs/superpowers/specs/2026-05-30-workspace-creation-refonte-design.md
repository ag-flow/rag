# Design — Refonte CreateWorkspaceDialog + immutabilité Reranking

**Date :** 2026-05-30
**Statut :** validé
**Prérequis :** spec vault-ownership (migration 029, owner_id disponible)

## Contexte

Le dialog de création de workspace demande actuellement une API key en clair et un choix de coffre — deux frictions UX importantes. Ce chantier remplace ces saisies par des selects de clés déjà stockées dans Harpocrate, et intègre la configuration du reranking à la création (immuable ensuite).

---

## Nouveau endpoint backend

### `GET /api/admin/provider-keys/by-provider`

```
GET /api/admin/provider-keys/by-provider?provider=openai
```

Retourne les `provider_api_keys` de tous les vaults accessibles au `current_owner` (vaults `is_default=true` OU `owner_id = current`), filtrées par `provider`.

**Response :** `list[ProviderApiKeyWithVault]` :
```
id          UUID
key_id      TEXT
label       TEXT
provider    TEXT
harpo_path  TEXT    -- vault_ref utilisé comme api_key_ref
vault_name  TEXT    -- pour affichage dans le select
vault_label TEXT
```

Fichiers :
- `backend/src/rag/api/admin_provider_keys.py` — nouvelle route
- `backend/src/rag/services/provider_api_keys.py` — nouvelle fonction `list_provider_keys_by_provider(conn, owner_id, provider)`
- `backend/src/rag/schemas/provider_api_keys.py` — nouveau DTO `ProviderApiKeyWithVault`

---

## Workspace creation — changements backend

### Schéma de création (payload)

**Avant :**
```
name            TEXT
api_key_vault   TEXT          -- nom du vault
indexer:
  provider      TEXT
  model         TEXT
  api_key       TEXT          -- clé en clair
  base_url      TEXT | null
```

**Après :**
```
name            TEXT
indexer:
  provider      TEXT
  model         TEXT
  api_key_ref   TEXT          -- vault_ref direct ex: ${vault://v1:/openai/prod-key}
  base_url      TEXT | null
rerank (optionnel):
  provider      TEXT
  model         TEXT
  api_key_ref   TEXT | null
  base_url      TEXT | null
  top_k_pre_rerank  INT
```

Le backend ne stocke plus rien dans Harpocrate à la création — il enregistre directement le `api_key_ref` fourni.

### Service `workspaces.create`

- Supprimer le code qui écrit dans Harpocrate (`set_secret`)
- Supprimer la résolution de vault par nom
- Accepter `api_key_ref` directement dans `indexer_configs`
- Si `rerank` fourni : créer la config rerank en même temps que le workspace (transaction atomique)

### Immutabilité du reranking

- **Supprimer** `PATCH /workspaces/{name}/rerank` (mise à jour)
- **Supprimer** `DELETE /workspaces/{name}/rerank` (suppression)
- **Conserver** `GET /workspaces/{name}/rerank` (lecture seule)
- La config rerank ne peut être créée qu'à la création du workspace et ne peut plus être modifiée ni supprimée

---

## Frontend

### `CreateWorkspaceDialog.tsx` — réécriture

Structure du formulaire :

```
[ Nom du workspace ]

─── Vectorisation ────────────────────────────────
  [Provider ▾]           [Modèle ▾]
  [URL base (si ollama/azure-openai)]
  [Clé API ▾]  ← select depuis useProviderKeysByProvider(provider)

─── Reranking (optionnel) ────────────────────────
  [Provider ▾]           [Modèle ▾]
  [URL base (si ollama)]
  [Clé API ▾]  ← même logique
  top_k_pre_rerank [input numérique]

[ Annuler ]                            [ Créer ]
```

**Providers dynamiques** : chargés depuis `useModels()` (table `model_dimensions`) — élimine la liste codée en dur.

**Select clé API** :
- Utilise `useProviderKeysByProvider(provider)` (nouveau hook)
- Affiche : `{label} — {key_id}` + sous-titre `{vault_label}`
- La valeur soumise = `harpo_path` (vault_ref)
- Si aucune clé disponible pour ce provider : message d'aide « Ajoutez d'abord une clé pour ce provider dans un coffre »

**Validators** :
- Vectorisation complète = nom + provider + modèle + clé API (sauf ollama qui n'en a pas)
- Reranking : soit entièrement vide, soit entièrement rempli (provider + modèle + clé si applicable + top_k)

### `WorkspaceRerankTab.tsx` — passage en lecture seule

Supprimer :
- Le formulaire react-hook-form
- Les boutons Save / Cancel / Delete / Activate
- L'état `deleteOpen` et `DeleteRerankAlert`
- L'import `DeleteRerankAlert`

Conserver :
- La bannière d'avertissement ambre
- L'affichage des valeurs

Nouveau rendu (miroir de `WorkspaceModelTab`) :

```tsx
<dl className="grid grid-cols-2 gap-2 text-sm">
  <dt>Provider</dt><dd>{data.provider}</dd>
  <dt>Modèle</dt><dd>{data.model}</dd>
  <dt>Base URL</dt><dd>{data.base_url ?? "—"}</dd>
  <dt>API key ref</dt><dd>{data.api_key_ref ?? "—"}</dd>
  <dt>top_k pré-rerank</dt><dd>{data.top_k_pre_rerank}</dd>
</dl>
<BanniereAmbre />
```

Si aucune config rerank → afficher « Aucun reranking configuré. »

### `WorkspaceModelTab.tsx` — déjà en lecture seule ✓

Aucun changement nécessaire.

### Nouveau hook `useProviderKeysByProvider`

```typescript
// frontend/src/hooks/useProviderKeys.ts (nouveau fichier)
export function useProviderKeysByProvider(provider: string | null) {
  return useQuery({
    queryKey: ["provider-keys-by-provider", provider],
    queryFn: () => adminApi.getProviderKeysByProvider(provider!),
    enabled: !!provider,
    staleTime: 30_000,
  });
}
```

### Nouveau type `ProviderApiKeyWithVault`

```typescript
export type ProviderApiKeyWithVault = {
  id: string;
  key_id: string;
  label: string;
  provider: string;
  harpo_path: string;
  vault_name: string;
  vault_label: string;
};
```

### i18n

Nouvelles clés dans `workspaces` namespace (FR + EN) :
```
form.indexer_section      "Vectorisation"
form.rerank_section       "Reranking (optionnel)"
form.api_key_ref          "Clé API"
form.api_key_ref_none     "Aucune clé disponible pour ce provider"
form.api_key_ref_help     "Clé stockée dans un coffre Harpocrate"
form.top_k                "top_k pré-rerank"
```

---

## Tests

### Backend
- `test_create_workspace_with_api_key_ref` — api_key_ref stocké directement, pas d'appel Harpocrate
- `test_create_workspace_with_rerank` — rerank_config créé atomiquement
- `test_provider_keys_by_provider_filters_owner` — ne retourne que les clés des vaults owner + défaut
- Vérifier que `PATCH /workspaces/{name}/rerank` n'existe plus (404)
- Vérifier que `DELETE /workspaces/{name}/rerank` n'existe plus (404)

### Frontend
- `CreateWorkspaceDialog` — soumet avec api_key_ref (pas api_key)
- Select clé API — chargé depuis useProviderKeysByProvider

---

## Périmètre hors-scope

- Modifier ou supprimer la config reranking après création (entièrement immuable)
- Modifier la config indexer après création (déjà immuable)
- Clés Git et SSH dans le dialog workspace (hors périmètre de ce chantier)
