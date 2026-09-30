# TypeScript / frontend ragflow

> Fragment généré depuis le standard globals « Fichier d'instructions — spécificités
> TypeScript / frontend » (révision 2026-09-24). À lire AVANT de modifier un fichier de
> `frontend/`.

### Conventions frontend

- TypeScript strict : `strict: true`, `noUncheckedIndexedAccess: true`
- Composants fonctionnels et hooks ; pas de classe
- **Tout appel API passe par TanStack Query** — jamais `useEffect` + `fetch` : un effet qui appelle sans annuler laisse une réponse tardive écraser un état courant
- i18n sur **tous** les libellés visibles — une chaîne en dur ne se traduit jamais après coup
- Fichiers max 300 lignes
- Vitest + React Testing Library ; `describe` / `it`, jamais `test`
- Props typées via `interface`, exports nommés.
- Libellés : un namespace i18n par écran dans `src/i18n/fr/*.json` et `src/i18n/en/*.json`.
- Couleurs : uniquement les tokens de la feuille de thème — `npm run lint` lance
  `scripts/check-colors.mjs`, qui refuse les couleurs en dur.

### Commandes

```bash
cd frontend && npm install
cd frontend && npm run dev              # :5173, proxy /api -> :8000
cd frontend && npm run typecheck        # tsc --noEmit
cd frontend && npm run lint             # eslint + contrôle des couleurs
cd frontend && npm run test:run         # Vitest, suite complète
cd frontend && npm run build            # tsc -b && vite build
cd frontend && npx prettier --check <fichiers du chantier>   # le dépôt a une config prettier
```

### Pièges connus

**Ne pas invoquer un formateur que le dépôt n'utilise pas.** `npx prettier --write` sur un dépôt sans configuration prettier télécharge l'outil et applique ses défauts — guillemets doubles, points-virgules — et reformate des fichiers entiers pour un ajout de trois lignes. Vérifier la présence d'une configuration avant, et s'en tenir à l'`eslint` du dépôt sinon.

**Un état semé depuis les props ne se recopie pas dans un effet.** `useEffect(() => setX(props.x))` fait écraser une saisie en cours par une réponse tardive ; dériver la valeur au rendu.

**Les tests qui montent un routeur ont besoin du chemin, pas seulement de l'élément.** Une route attrape-tout rend `useParams()` vide, et les tests échouent pour une raison sans rapport avec ce qu'ils vérifient.

**Un jeu d'essai qui porte déjà la valeur attendue rend le test aveugle.** Si la doublure a un champ vide et que le test vérifie qu'il est vide, il restera vert même si le code le recopie. Éprouver le test en cassant le code.

### Part de checklist frontend

- [ ] `tsc --noEmit` et `eslint` passent
- [ ] La suite Vitest passe en entier, pas seulement les fichiers touchés
- [ ] Aucun libellé en dur : tout passe par i18n, dans **toutes** les langues du dépôt
- [ ] Aucun appel API hors TanStack Query
- [ ] Aucun reformatage massif hors périmètre dans le diff
