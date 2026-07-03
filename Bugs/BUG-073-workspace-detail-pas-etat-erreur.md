# BUG-073 — Détail workspace : pas d'état d'erreur → spinner infini ou rendu périmé pour un workspace supprimé/inconnu

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : haute
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/workspace/WorkspaceDetailPanel.tsx:31-37`, `frontend/src/pages/WorkspacesPage.tsx:17-24`, `frontend/src/pages/workspace/DeleteWorkspaceAlert.tsx:40`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

`WorkspaceDetailPanel` ne gère que `isLoading || !ws` (spinner) — pas de branche `isError`. Un 404 sur `useWorkspace` (après 3 retries) laisse un spinner permanent ; s'il existe des données de cache périmées pour cette clé, le panneau rend le workspace supprimé comme s'il était vivant. Aggravant : après suppression, `navigate("/workspaces")` efface `?ws`, et l'effet d'auto-sélection prend immédiatement `data[0]` du cache `["workspaces"]` encore périmé — qui peut être le workspace tout juste supprimé.

## Scénario de défaillance

Supprimer le premier workspace de la liste → redirection vers `/workspaces` → l'auto-select re-sélectionne le workspace supprimé depuis la liste périmée → le panneau de détail spin pour toujours (ou montre le workspace mort) alors que la sidebar ne le contient plus. Idem pour une URL bookmarkée avec un `?ws=` périmé. (Comparaison : `VaultDetailPanel` gère `isError` correctement.)

## Code concerné

```tsx
if (isLoading || !ws) {
  return (<div className="flex flex-1 items-center justify-center"><LoadingSpinner /></div>);
}
```

## Piste de correction

Ajouter une branche `isError` dans `WorkspaceDetailPanel` ; après suppression, retirer l'entrée cache `["workspace", name]` et/ou gater l'auto-select jusqu'à ce que le refetch de la liste soit stabilisé.
