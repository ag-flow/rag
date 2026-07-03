# BUG-018 — `useLastTestResult` lit le cache React Query de façon non réactive

**Statut : 🔴 à corriger**

- **Zone** : frontend / hooks (harpocrate)
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/hooks/useHarpocrateVaults.ts:126-130` (writer en 115-124), consommateur `VaultHeader.tsx`
- **Modèle recommandé pour la correction** : **Sonnet** (`claude-sonnet-5`) — réécrire en useQuery désactivée / useSyncExternalStore

## Description

`useLastTestResult` appelle `qc.getQueryData(...)` directement, sans `useQuery`, donc aucune souscription n'existe — le composant n'est pas re-rendu quand `useTestConnection.onSuccess` écrit la valeur via `setQueryData`. Ça fonctionne aujourd'hui par accident : le seul appelant (`VaultHeader.tsx`) possède aussi la mutation, dont le changement d'état force un re-render. À noter aussi le `return null` anticipé avant `getQueryData` — le nombre de hooks reste constant (seul `useQueryClient` est un hook) donc pas de violation des règles de hooks, mais c'est fragile.

## Scénario de défaillance

1. Un second composant (ex. la liste de vaults avec un point de santé) consomme `useLastTestResult(vault.id)` alors que le bouton de test vit dans `VaultHeader`.
2. L'utilisateur clique « Test connection » ; le header se met à jour mais l'autre composant continue d'afficher la valeur pré-test jusqu'à un re-render sans rapport.

## Code concerné

```ts
export function useLastTestResult(id: string | null): VaultTestConnectionResult | null {
  const qc = useQueryClient();
  if (!id) return null;
  return qc.getQueryData<VaultTestConnectionResult>([...ROOT_KEY, id, "lastTest"]) ?? null;
}
```

## Piste de correction

L'implémenter comme `useQuery({ queryKey: [...ROOT_KEY, id, "lastTest"], enabled: false, ... })` ou avec `queryClient.getQueryState` + souscription (`useSyncExternalStore`), pour que les écritures cache se propagent.
