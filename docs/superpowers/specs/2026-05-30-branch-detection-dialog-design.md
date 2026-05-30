# Design — Détection automatique des branches dans AddSourceDialog

**Date :** 2026-05-30
**Statut :** validé

## Contexte

Dans le dialog d'ajout de source Git, le champ Branch est un Input texte libre. Ce chantier le remplace par un Select dynamique : après 800ms de debounce sur le champ URL, le backend interroge le remote via `git ls-remote --heads` et retourne la liste des branches disponibles. La branche par défaut est pré-sélectionnée.

---

## Backend

### Nouvelle fonction `list_remote_branches` dans `git_ops.py`

```python
async def list_remote_branches(
    *,
    url: str,
    token: str | None = None,
    ssh_key: str | None = None,
    ssh_username: str | None = None,
    deadline: float = 10.0,
) -> list[str]:
```

Utilise `git ls-remote --heads <url>` pour lister toutes les branches. Parse les lignes du format `<sha>\trefs/heads/<branch>`. Retourne `[]` en cas d'erreur (timeout, auth, réseau).

Le default branch reste détecté par `detect_default_branch` existant (`git ls-remote --symref`).

### Nouveau endpoint

```
POST /api/admin/sources/detect-branches
Auth : require_master_key_or_authenticated_admin
Body :
  url          str
  auth_ref     str | None
  ssh_key_ref  str | None
  ssh_username str | None

Response 200 :
  branches  list[str]   — triées alphabétiquement
  default   str | None  — branche par défaut (HEAD symref)
```

Le endpoint résout `auth_ref` ou `ssh_key_ref` via le resolver, puis appelle `list_remote_branches` et `detect_default_branch` en parallèle (`asyncio.gather`). En cas d'échec partiel : retourne ce qui a pu être obtenu, sans lever d'erreur HTTP.

**Fichiers :**
- `backend/src/rag/sync/git_ops.py` — ajouter `list_remote_branches`
- `backend/src/rag/api/admin.py` — ajouter l'endpoint dans `build_admin_router`

---

## Frontend

### Hook `useDetectBranches`

```typescript
// Mutation TanStack Query — appelée manuellement au debounce
export function useDetectBranches() {
  return useMutation({
    mutationFn: (payload: {
      url: string;
      auth_ref?: string;
      ssh_key_ref?: string;
      ssh_username?: string;
    }) => api.post<{ branches: string[]; default: string | null }>(
      "/api/admin/sources/detect-branches",
      payload
    ),
  });
}
```

### Comportement dans `AddSourceDialog`

1. URL change → debounce 800ms
2. Si `url.length > 10` ET provider sélectionné → appel `detectBranches.mutate({url, auth_ref, ssh_key_ref, ssh_username})`
3. Pendant l'appel : spinner `🔄` à côté du label Branch
4. Résultats disponibles :
   - `branches.length === 0` → fallback Input texte libre
   - `branches.length === 1` → auto-sélection silencieuse (pas de Select visible si désiré, ou Select avec une seule option)
   - `branches.length > 1` → Select peuplé, `default` pré-sélectionné si présent
5. L'utilisateur peut toujours taper une valeur libre (fallback)

### Layout du champ Branch

```
Branche
[  main ▾  ]  🔄   ← spinner pendant fetch
```

Quand aucun résultat : `Input` classique avec placeholder `"main"`.

---

## Tests

- `test_list_remote_branches_parses_heads` — mock git output → liste correcte
- Endpoint `detect-branches` : mock `list_remote_branches` + `detect_default_branch` → response correcte

---

## Périmètre hors-scope

- Rafraîchir la liste si le credential change (l'utilisateur re-tape l'URL pour re-déclencher)
- Pagination des branches (> 100 branches)
