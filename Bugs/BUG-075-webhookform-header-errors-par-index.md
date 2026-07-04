# BUG-075 — WebhookForm : map d'erreurs de header clée par index, non ré-indexée à la suppression

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/WebhookForm.tsx:52-59` (aussi 29-46)
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`headerErrors` est un `Record<number, string>` clé par index de tableau. `removeHeader(idx)` supprime l'erreur à `idx` mais ne décale pas les erreurs pour les index > idx, alors que le tableau de headers se compacte.

## Scénario de défaillance

Header 0 = « X-Api-Key » (valide), header 1 = « X-Rag-Signature » (réservé → erreur à l'index 1). L'utilisateur supprime le header 0. Le header réservé est maintenant à l'index 0 sans erreur, et une erreur *périmée* siège sous l'index 1 — affichée contre le header qui occupe le slot 1, et `hasReservedError` garde la soumission bloquée (ou inversement, laisse le header réservé soumissible).

## Code concerné

```ts
function removeHeader(idx: number) {
  setHeaders((h) => h.filter((_, i) => i !== idx));
  setHeaderErrors((e) => { const copy = { ...e }; delete copy[idx]; return copy; });
}
```

## Piste de correction

Stocker les erreurs sur les objets header eux-mêmes (ou utiliser un id stable par ligne), ou recalculer toutes les erreurs depuis `headers` à chaque changement.
