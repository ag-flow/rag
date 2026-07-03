# BUG-076 — Les mutations create/toggle/delete de webhook n'ont aucun retour d'erreur ; une création échouée laisse le dialog ouvert silencieusement

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/WorkspaceWebhooksTab.tsx:49-69`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`createMutation`, `toggleMutation`, `deleteMutation` ne définissent que `onSuccess`. En cas d'échec rien ne se passe — pas de toast, pas de message, le dialog reste ouvert avec l'état spinner effacé.

## Scénario de défaillance

Le backend rejette la création de webhook (URL invalide, 422, erreur réseau). Le bouton « Save » se réactive, le formulaire reste silencieusement là ; l'utilisateur suppose que c'est sauvegardé et ferme le dialog — le webhook n'a jamais été créé.

## Code concerné

```ts
const createMutation = useMutation({
  mutationFn: (payload) => createWebhook(workspaceName, payload),
  onSuccess: () => { ...; setShowForm(false); },
});  // pas d'onError
```

## Piste de correction

Ajouter des handlers `onError` avec des toasts destructifs, comme partout ailleurs dans ce codebase.
