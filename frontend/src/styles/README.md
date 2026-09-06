# Fondations CSS — tokens

**Source de vérité : `src/styles/tokens.css`** (enabler docflow `75058a6a`).

## Où sont les tokens

- `tokens.css` — couleurs (rampes 100→900 par rôle : `neutral`, `accent` acier,
  `success`, `warning`, `danger`), typographie (`--font-display` condensée,
  `--font-body`, échelle de tailles/graisses/interlignes), espacements
  (`--space-*`), rayons/ombres (3 niveaux max), états (`--focus-ring-*`,
  `--disabled-opacity`), densité (`--density-*`).
- `globals.css` — normalisation navigateur (liens, `::selection`,
  `:focus-visible`, contrôles natifs, disabled) + utilitaires de densité
  (`density-nav`, `density-row`, `density-card`).
- `tailwind.config.js` — mappe **toutes** les palettes Tailwind du code
  existant (slate, sky, emerald, amber, rose, red, blue…) sur les rampes de
  rôle. Changer une valeur dans `tokens.css` propage partout.

## Comment ajouter un token

1. Déclarer la variable dans `tokens.css` (format RGB `R G B` pour les
   couleurs, afin de composer l'opacité).
2. Si elle doit être consommable en classe Tailwind, l'exposer dans
   `tailwind.config.js`.
3. Ne jamais écrire la valeur en dur dans un écran.

## Ce qu'on n'écrit plus à la main

- Couleurs hexadécimales dans les composants ou le CSS des écrans —
  **contrôlé par `npm run lint`** (`scripts/check-colors.mjs`, exceptions
  listées et justifiées dans le script).
- États de survol/pressé improvisés : prendre le pas de rampe suivant
  (600 → 700 → 800).
- Anneaux de focus ou couleurs de lien par défaut du navigateur : gérés
  globalement dans `globals.css`.
- Paddings de liste/carte fixes sur les écrans denses : utiliser
  `density-row` / `density-card` (axe aéré/compact piloté par
  `data-density` sur `<html>`, préférence dans Mon profil).

## Densité

`localStorage["rag-density"]` + attribut `data-density` sur `<html>`
(`comfortable` par défaut, `compact`). Voir `src/lib/density.ts`.
