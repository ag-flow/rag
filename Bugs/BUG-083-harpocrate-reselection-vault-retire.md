# BUG-083 — La page Harpocrate peut re-sélectionner un vault tout juste retiré depuis le cache périmé

**Statut : 🟢 corrigé**

- **Zone** : frontend / pages/harpocrate
- **Sévérité** : basse
- **Complexité** : simple
- **Fichiers** : `frontend/src/pages/HarpocrateVaultsPage.tsx:19-27`, `frontend/src/pages/harpocrate/VaultDetailPanel.tsx:33-37`
- **Modèle recommandé** : **Sonnet** (`claude-sonnet-5`)

## Description

Même pattern que BUG-073, plus léger : après que `RetireVaultDialog` efface `?vault`, l'effet d'auto-select tourne contre le cache `["vaults"]` encore périmé (refetch d'invalidation en vol) et peut sélectionner le vault retiré (souvent le défaut, que l'effet préfère). Contrairement aux workspaces, le panneau rend bien un état d'erreur, donc l'impact est un panneau « load error » parasite au lieu d'un hang.

## Scénario de défaillance

Retirer le vault par défaut → l'URL est immédiatement re-remplie avec l'id du vault retiré → panneau rouge « detail.load_error » jusqu'à ce que l'utilisateur clique sur un autre vault.

## Code concerné

```ts
const defaultVault = data.find((v) => v.is_default) ?? data[0];
if (defaultVault) { setSearchParams({ vault: defaultVault.id }, { replace: true }); }
```

## Piste de correction

Après retrait, `qc.removeQueries` pour le vault et sauter l'auto-select tant que `isFetching` sur la liste.
