# BUG-072 — Détection de branche : races non gardées et pas d'annulation des requêtes en vol

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : modérée
- **Fichiers** : `frontend/src/pages/workspace/AddSourceDialog.tsx:275-306`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — séquençage de requêtes, staleness

## Description

Chaque changement débounced appelle `detectBranches.mutate(...)` ; les réponses sont appliquées dans l'ordre d'arrivée sans check de staleness, et l'effet ne vérifie pas `open`. Deux requêtes qui se chevauchent (URL éditée deux fois, ou URL puis credential) peuvent résoudre dans le désordre ; une réponse d'une session de dialog précédente peut aussi arriver après fermeture/réouverture.

## Scénario de défaillance

L'utilisateur tape l'URL du repo A, corrige vite en repo B. La requête A résout en dernier → `detectedBranches` montre les branches du repo A et `setValue("branch", A_default)` remplit une branche inexistante dans le repo B ; la source est créée pointant vers une branche inexistante.

## Code concerné

```ts
onSuccess: (data) => {
  setDetectedBranches(data.branches);
  ...
  if (!createForm.getValues("branch")) createForm.setValue("branch", target);
},
```

## Piste de correction

Suivre un numéro de séquence de requête / comparer contre le `watchedUrl` courant dans `onSuccess`, et bail quand `!open`.
