# BUG-081 — TriggerPromptsPanel : `order_index` dupliqué après suppressions ; erreurs d'ajout avalées

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/WorkspaceTriggersTab.tsx:40-52`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`nextOrder = triggerPrompts.length + 1` ne tient pas compte des trous. Avec des prompts aux orders 1 et 3 (après suppression du 2), le prochain ajout obtient `order_index = 3` — un doublon. De plus `handleAddPrompt` await `mutateAsync` sans try/catch : en cas d'échec la promise reject non gérée, pas de toast, et le mini-form reste silencieusement ouvert.

## Scénario de défaillance

Ajouter les prompts A(1), B(2), C(3) ; supprimer B ; ajouter D → D obtient l'order 3, en collision avec C ; l'ordre d'exécution des enrichissements devient ambigu. Séparément, un 409/422 à l'ajout ne donne aucun retour utilisateur.

## Code concerné

```ts
const nextOrder = triggerPrompts.length + 1;
...
await addPrompt.mutateAsync({ template_id: ..., llm_id: ..., order_index: nextOrder });
```

## Piste de correction

`nextOrder = max(order_index) + 1` ; envelopper le mutate dans try/catch avec un toast d'erreur.
