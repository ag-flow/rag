# BUG-078 — AddSourceDialog : le toast d'avertissement de branche est instantanément remplacé (TOAST_LIMIT = 1)

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/AddSourceDialog.tsx:355-362`, `components/ui/use-toast.ts:6`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

À la création réussie, deux toasts partent coup sur coup : `branch_warning` puis `success`. Le store de toast shadcn a `TOAST_LIMIT = 1`, donc le toast de succès remplace l'avertissement avant qu'il puisse être lu.

## Scénario de défaillance

Le backend signale que la branche demandée n'existe pas (`branch_warning`) ; l'utilisateur ne voit que « Source added » et n'apprend jamais que la branche a fallback / est invalide.

## Code concerné

```ts
if (created.branch_warning) { toast({ title: t("sources.add.branch_warning") }); }
toast({ title: t("sources.add.success") });
```

## Piste de correction

Fusionner en un seul toast (title = success, description = warning) ou afficher l'avertissement inline dans la liste des sources.
