# BUG-077 — CreateWorkspaceDialog : défauts de formulaire calculés avant le chargement des modèles et jamais re-synchronisés

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/workspace
- **Sévérité** : moyenne
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/CreateWorkspaceDialog.tsx:194-211`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`defaultProvider`/`defaultModel` sont dérivés de `models` au premier render, mais le dialog est monté (fermé) au mount de la page pendant que `useModels()` est encore en vol — donc `useForm` capture `provider: "openai"`, `model: ""` et ne se met jamais à jour à l'arrivée des modèles (`defaultValues` n'est lu qu'une fois ; pas de reset à l'ouverture).

## Scénario de défaillance

Sur une session fraîche, ouvrir « Create workspace » : le select provider montre « openai » même si aucun modèle openai n'est enregistré, et le select modèle est vide ; soumettre échoue le `model: min(1)` de zod sans cause évidente.

## Code concerné

```ts
const defaultProvider = [...new Set(models.map((m) => m.provider))].sort()[0] ?? "openai";
const form = useForm<FormData>({ ...,
  defaultValues: { name: "", indexer: { provider: defaultProvider, model: defaultModel, ... } },
});
```

## Piste de correction

`form.reset(...)` avec les défauts calculés à l'ouverture du dialog (effet sur `open` + `models`), comme le font `AddModelDialog`/`AddSourceDialog`.
