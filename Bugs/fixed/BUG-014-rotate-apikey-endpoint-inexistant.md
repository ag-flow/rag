# BUG-014 — `rotateApiKey` appelle un endpoint backend qui n'existe pas

**Statut : 🟢 corrigé**

- **Zone** : frontend / lib + hooks (code latent)
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/lib/workspaces.ts:34-35`, `frontend/src/hooks/useWorkspaces.ts:89-97`, `frontend/src/components/RotateApiKeyDialog.tsx` (non monté)
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — suppression du code mort ou ajout de la route

## Description

`workspacesApi.rotateApiKey` fait `POST /api/admin/workspaces/{name}/rotate-apikey`. Un grep de tout le backend (`backend/src/rag/`) ne trouve aucune route de ce type — seuls existent `GET /workspaces/{name}/apikey` (`admin/__init__.py:127`) et le plus récent `POST /workspaces/{name}/api-keys/{key_id}/rotate` (`admin/__init__.py:804`). La chaîne `rotate-apikey` n'apparaît que dans une docstring de schéma. `RotateApiKeyDialog.tsx` (qui utilise ce hook) n'est actuellement importé par aucune page montée — bug latent, mais la fonction API est cassée telle que livrée.

## Scénario de défaillance

Si une page monte `RotateApiKeyDialog` (ou appelle `useRotateApiKey` de `useWorkspaces`), la mutation échoue systématiquement en 404/405 ; l'UI affiche une erreur et aucune clé n'est jamais tournée.

## Code concerné

```ts
rotateApiKey: (name: string) =>
  api.post<ApiKeyRotateResponse>(`${BASE}/${name}/rotate-apikey`, {}),
```

## Piste de correction

Soit supprimer `rotateApiKey`/`useRotateApiKey`/`RotateApiKeyDialog` (supplantés par `useWorkspaceApiKeys.useRotateApiKey` qui tape `/api-keys/{keyId}/rotate`), soit ajouter la route backend.
