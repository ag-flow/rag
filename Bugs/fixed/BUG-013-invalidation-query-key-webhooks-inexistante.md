# BUG-013 — Enable/disable webhook invalide une query key qu'aucune query n'utilise : liste des sources jamais rafraîchie

**Statut : 🟢 corrigé**

- **Zone** : frontend / hooks
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `frontend/src/hooks/useSourceWebhooks.ts:10,21` (vs `frontend/src/hooks/useWorkspaces.ts:32-38`)
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — corriger la clé, idéalement extraire des key factories partagées

## Description

`useEnableWebhook` / `useDisableWebhook` invalident `["sources", workspaceName]`, mais la liste des sources est cachée sous `["workspace", name, "sources"]` (cf. `useWorkspaceSources`). Vérifié par grep : aucune query n'enregistre la clé `["sources", ...]`. L'invalidation est un no-op silencieux.

## Scénario de défaillance

1. L'utilisateur active un webhook sur une source git dans `WorkspaceSourcesTab` (qui affiche le badge `source.webhook_enabled` depuis les données de `useWorkspaceSources`).
2. La mutation réussit, mais le badge et le menu d'action enable/disable affichent toujours l'ancien état, car la vraie query n'est jamais invalidée et les defaults globaux sont `staleTime: 30_000`, `refetchOnWindowFocus: false`.
3. Idem au disable : le dialog se ferme mais le badge « webhook » reste.

## Code concerné

```ts
onSuccess: () => {
  void qc.invalidateQueries({ queryKey: ["sources", workspaceName] });
},
```

## Piste de correction

Invalider `["workspace", workspaceName, "sources"]`. Idéalement, extraire des key factories partagées pour empêcher toute dérive future entre hooks.
