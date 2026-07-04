# BUG-082 — `CleaningOptionsPanel` n'est jamais monté — la feature d'options de nettoyage est inaccessible depuis l'UI

**Statut : ✅ corrigé**

## Résolution (full-stack sur le moteur legacy)

La piste initiale (« câbler le panneau + merger dans `extras` ») était **incomplète** :
le nettoyage n'était consommé que par le moteur `structured`
(`chunking_strategies.params`), alors que `WorkspaceChunkingTab` pilote le moteur
`legacy` (`paragraph`/`markdown`), qui l'ignorait totalement. Câbler seulement le
frontend aurait produit des toggles sans effet. Correction retenue (décision
architecte : rendre le nettoyage réellement effectif via l'onglet) :

- **Backend `cleaner.py`** : extraction de l'ordre de nettoyage dans une fonction
  pure partagée `apply_cleaning` + nouveau `CleaningLegacyChunkerWrapper`
  (`ChunkerProtocol`, `list[Chunk]`) réutilisant cette logique sans duplication.
- **Backend `factory.py`** : `make_chunker` extrait les 4 clés booléennes de
  `extras` et enveloppe le chunker si au moins une est activée.
- **Backend `admin.py`** : `_validate_extras` accepte désormais les clés de
  nettoyage (booléens) pour `paragraph` et `markdown`, en plus de `heading_levels`.
- **Frontend** : `CleaningOptionsPanel` monté dans `WorkspaceChunkingTab` via
  react-hook-form (source unique) ; `chunkingExtras.ts` mappe `extras` ↔ options
  et porte les toggles activés dans le payload. Un changement d'option modifie
  `extras` → déclenche la détection de réindexation existante (`jobs.py`).

Tests : schéma + factory backend (validés par comportement, deps pytest non
installées dans le conteneur), `chunkingExtras` + `WorkspaceChunkingTab` frontend
(33 tests verts, 0 régression).

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
