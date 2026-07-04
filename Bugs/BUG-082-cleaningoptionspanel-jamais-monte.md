# BUG-082 — `CleaningOptionsPanel` n'est jamais monté — la feature d'options de nettoyage est inaccessible depuis l'UI

**Statut : 🔴 à corriger**

- **Zone** : frontend / pages/workspace
- **Sévérité** : basse
- **Complexité** : modérée
- **Confiance** : faible (peut être volontairement mis en attente pour un jalon ultérieur)
- **Fichiers** : `frontend/src/pages/workspace/CleaningOptionsPanel.tsx` (composant) ; consommateur attendu `WorkspaceChunkingTab.tsx`
- **Modèle recommandé** : **Opus** (`claude-opus-4-8`) — câblage payload extras + validation par stratégie côté backend

## Description

`CleaningOptionsPanel` + son schéma (`clean_content`, `strip_separators`, `strip_boilerplate`, `strip_html`) sont pleinement implémentés mais importés nulle part (grep confirme zéro usage hors de ses propres fichiers/tests). Le `computeExtrasPayload` de l'onglet chunking ne porte jamais non plus les options de nettoyage — les extras sont soit passés inchangés soit reset à `{}`.

## Scénario de défaillance

La feature de nettoyage par stratégie (commit 4c53e05) ne peut être activée depuis l'UI admin ; les switches, strings i18n et schéma sont du code mort.

## Code concerné

```ts
export function CleaningOptionsPanel({ value, onChange, disabled = false }: Props) { ... } // 0 usages
```

## Piste de correction

Câbler le panneau dans `WorkspaceChunkingTab` et merger ses valeurs dans le payload `extras` (en respectant la validation d'extras par stratégie du backend). À confirmer si c'est un choix de jalon avant de corriger.
