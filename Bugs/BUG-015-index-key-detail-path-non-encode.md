# BUG-015 — `getIndexKeyDetail` n'encode pas le path du document (le PATCH voisin, si)

**Statut : 🟢 corrigé**

- **Zone** : frontend / lib
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/lib/workspaces.ts:76-77` (contraste ligne 80)
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — un `encodeURIComponent`

## Description

Le GET interpole `path` brut dans l'URL alors que `patchIndexKeyStrategy` l'enveloppe dans `encodeURIComponent`. La route backend est `GET /workspaces/{name}/index-keys/{path:path}` (`backend/src/rag/api/admin_index_keys.py:108`), donc les slashes passent, mais un path contenant `?`, `#` ou `%` casse : `?` tronque le path en query string, `#` le tronque en fragment (jamais envoyé), et un `%` nu produit un percent-encoding invalide qu'uvicorn rejette en 400.

## Scénario de défaillance

1. Un repo/source contient un fichier type `docs/faq?.md`, `c#/notes.md` ou `charge 100%.md`.
2. La liste des index-keys l'affiche, mais cliquer pour ouvrir le détail émet une requête malformée → 404/400 → le panneau de détail plante, alors que le PATCH de stratégie sur le **même** path fonctionne (encodé). Cassure incohérente et dépendante du path.

## Code concerné

```ts
getIndexKeyDetail: (name: string, path: string) =>
  api.get<PathDetailResponse>(`${BASE}/${name}/index-keys/${path}`),
...
patchIndexKeyStrategy: (name, path, payload) =>
  api.patch<void>(`${BASE}/${name}/index-keys/${encodeURIComponent(path)}/strategy`, payload),
```

## Piste de correction

`encodeURIComponent(path)` dans `getIndexKeyDetail`, aligné sur le PATCH (le `%2F` encodé est re-décodé en `/` à la couche ASGI, comme le PATCH fonctionnel le démontre déjà).
