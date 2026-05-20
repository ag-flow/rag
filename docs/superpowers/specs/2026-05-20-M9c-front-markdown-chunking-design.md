# M9c-front — Exposer la stratégie markdown dans l'IHM Chunking

> **Statut** : design validé pour implémentation.
> **Spec produit ciblée** : `specs/09-roadmap.md` § « Amélioration du chunking » — ligne « M9c-front : exposer `markdown` dans l'IHM workspace ».
> **Prérequis** : M9b (onglet Chunking livré), M9c backend (strategy markdown livrée et configurable via API admin).
> **Hors-scope explicite** : édition de `heading_levels` côté IHM (reste pilotable uniquement via API admin), preview du chunking, modification backend.

---

## 1. Contexte et motivation

M9c a livré côté backend la stratégie sémantique `markdown` (configurable via `PUT /chunking-config` avec `strategy='markdown'` + `extras.heading_levels`). Le frontend M9b expose toujours uniquement `paragraph` dans son enum Zod : la stratégie `markdown` est donc accessible uniquement aux administrateurs qui passent par l'API.

M9c-front élargit l'enum frontend pour rendre `markdown` sélectionnable dans le Select Stratégie de l'onglet Chunking (`WorkspaceChunkingTab`), avec helper text dédié. Le champ `heading_levels` n'est volontairement **pas** exposé dans l'IHM : il reste fixé au default backend `[1, 2]` lors d'une sélection IHM, et peut continuer à être customisé par un admin via API (la config admin est alors préservée par la logique pass-through, cf. §4).

Bénéfice : l'utilisateur peut basculer un workspace vers le chunking markdown sans connaître l'API admin. La complexité de `heading_levels` reste cachée tant qu'un besoin produit n'émergera pas (potentiel jalon ultérieur si l'usage le justifie).

---

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Pas d'UI pour `heading_levels` | YAGNI. Default `[1, 2]` couvre 90 % des cas. Évite d'introduire un multi-select chips/checkboxes dont la validation Zod miroir du backend (1..6, triés, sans doublon) gonflerait le scope |
| D2 | Helper text **pédagogique** (variante B) | « Respecte la structure d'un document Markdown : un chunk = une section délimitée par les titres (H1, H2 par défaut). Les blocs de code (```) ne sont jamais coupés. » Donne le modèle mental sans afficher la config technique |
| D3 | Label `Markdown` (pas `Markdown (par sections)`) | Asymétrie volontaire avec `Paragraphs (default)` : « (par défaut) » suffit à marquer le défaut, ajouter « (par sections) » à markdown serait du bruit visuel |
| D4 | Logique `extras` pass-through (helper externe) | Si `strategy` inchangée → renvoie `data.extras` tel quel (préserve un `heading_levels` custom posé via API admin). Si `strategy` changée → renvoie `{}` (le backend applique son default). Évite la régression silencieuse de la config admin quand un user édite uniquement `max_chars` |
| D5 | Helper `computeExtrasPayload` extrait dans `lib/chunkingExtras.ts` | Testable en isolation (4 tests purs, pas de RTL). Documente explicitement la règle au lieu d'une ternaire perdue dans onSubmit |
| D6 | Pas de modification de `DEFAULT_CHUNKING_FORM` | Reste `paragraph` à la création de workspace. Le default backend n'a pas changé en M9c |
| D7 | Pas de changement backend | M9c backend déjà livré et testé. Contrat API inchangé |
| D8 | Tests : helper pur + schema + composant | Couverture en pyramide : 4 tests purs (helper), 2-3 schema, 4 composant. ~10-11 nouveaux tests |

---

## 3. Inventaire des fichiers

### 3.1 Fichiers à modifier

| Fichier | Modification |
|---|---|
| `frontend/src/lib/chunking.types.ts` | `type ChunkingStrategy = "paragraph"` → `"paragraph" \| "markdown"` |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` | `CHUNKING_STRATEGIES = ["paragraph"]` → `["paragraph", "markdown"]` ; `z.enum(["paragraph"])` → `z.enum(["paragraph", "markdown"])` |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | Remplacer `extras: {}` dans `onSubmit` par appel à `computeExtrasPayload(values.strategy, data)` + import |
| `frontend/src/i18n/fr/workspace.json` | +2 clés sous `chunking.fields` : `strategies.markdown`, `strategyHelp.markdown` |
| `frontend/src/i18n/en/workspace.json` | +2 clés sous `chunking.fields` : `strategies.markdown`, `strategyHelp.markdown` |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts` | +2 à +3 tests (markdown accepté, enum inconnue rejetée, `CHUNKING_STRATEGIES` exposé dans l'ordre attendu) |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx` | +4 tests (Select offre 2 options, helper change, submit extras `{}` après changement, submit pass-through si strategy inchangée) |
| `specs/09-roadmap.md` | Marquer M9c-front livré (à la fin du jalon) |

### 3.2 Fichiers à créer

| Fichier | Responsabilité |
|---|---|
| `frontend/src/lib/chunkingExtras.ts` | Helper pur `computeExtrasPayload(nextStrategy, current): Record<string, unknown>` |
| `frontend/src/lib/__tests__/chunkingExtras.test.ts` | 4 tests unitaires du helper |

Pas de fichier backend touché. Pas de migration. Pas de hook React modifié (`useChunking.ts` est générique sur `ChunkingStrategy`, s'élargit automatiquement).

---

## 4. Helper `computeExtrasPayload`

### 4.1 Signature et implémentation

```typescript
// frontend/src/lib/chunkingExtras.ts
import type { ChunkingConfig, ChunkingStrategy } from "@/lib/chunking.types";

/**
 * Calcule le payload `extras` à envoyer au PUT /chunking-config.
 *
 * Règle :
 * - Si la strategy change → renvoie {} (le backend appliquera son default,
 *   notamment {heading_levels:[1,2]} pour markdown).
 * - Si la strategy ne change pas → renvoie current.extras tel quel (pass-through),
 *   pour préserver un heading_levels custom posé via API admin.
 *
 * @param nextStrategy - strategy choisie dans le form
 * @param current - config courante renvoyée par le backend
 */
export function computeExtrasPayload(
  nextStrategy: ChunkingStrategy,
  current: ChunkingConfig,
): Record<string, unknown> {
  return nextStrategy === current.strategy ? current.extras : {};
}
```

### 4.2 Intégration dans `WorkspaceChunkingTab.tsx`

```diff
+ import { computeExtrasPayload } from "@/lib/chunkingExtras";

  const onSubmit = (values: ChunkingFormValues) => {
-   const payload: ChunkingSpec = { ...values, extras: {} };
+   const payload: ChunkingSpec = {
+     ...values,
+     extras: computeExtrasPayload(values.strategy, data),
+   };
    upsert.mutate(...);
  };
```

`data` est garanti non-undefined à ce point du composant : le rendu du formulaire est bloqué par `if (isLoading || !data) return <LoadingSpinner />` plus haut.

### 4.3 Matrice de comportement

| `current.strategy` | `nextStrategy` | `current.extras` | Renvoyé | Justification |
|---|---|---|---|---|
| `paragraph` | `paragraph` | `{}` | `{}` | Pass-through trivial |
| `paragraph` | `markdown` | `{}` | `{}` | Backend normalisera en `{heading_levels:[1,2]}` |
| `markdown` | `paragraph` | `{heading_levels:[1,2]}` | `{}` | Sinon le backend rejette (paragraph n'accepte pas d'extras) |
| `markdown` | `markdown` | `{heading_levels:[1,3]}` | `{heading_levels:[1,3]}` | Pass-through : préserve la conf admin |

---

## 5. Changements i18n

### 5.1 FR — `frontend/src/i18n/fr/workspace.json` (bloc `chunking.fields`)

```diff
  "fields": {
    "strategy": "Stratégie",
    "strategyHelp": {
-     "paragraph": "Découpage par paragraphes avec coalesce des petits et split des gros."
+     "paragraph": "Découpage par paragraphes avec coalesce des petits et split des gros.",
+     "markdown": "Respecte la structure d'un document Markdown : un chunk = une section délimitée par les titres (H1, H2 par défaut). Les blocs de code (```) ne sont jamais coupés."
    },
-   "strategies": { "paragraph": "Paragraphes (par défaut)" },
+   "strategies": {
+     "paragraph": "Paragraphes (par défaut)",
+     "markdown": "Markdown"
+   },
```

### 5.2 EN — `frontend/src/i18n/en/workspace.json` (bloc symétrique)

```diff
  "fields": {
    "strategy": "Strategy",
    "strategyHelp": {
-     "paragraph": "Paragraph splitting with coalesce of small chunks and split of large ones."
+     "paragraph": "Paragraph splitting with coalesce of small chunks and split of large ones.",
+     "markdown": "Follows the structure of a Markdown document: one chunk = one section delimited by headings (H1, H2 by default). Code fences (```) are never split."
    },
-   "strategies": { "paragraph": "Paragraphs (default)" },
+   "strategies": {
+     "paragraph": "Paragraphs (default)",
+     "markdown": "Markdown"
+   },
```

### 5.3 Convention de label

L'asymétrie « Paragraphes (par défaut) » / « Markdown » est volontaire : le « (par défaut) » sur paragraph signale le défaut sans surcharger markdown. Mêmes règles pour l'EN (« Paragraphs (default) » / « Markdown »).

---

## 6. Schéma Zod et type

### 6.1 `chunking.types.ts`

```diff
- export type ChunkingStrategy = "paragraph";
+ export type ChunkingStrategy = "paragraph" | "markdown";
```

Le commentaire en tête de fichier rappelle déjà « Miroir des schemas Pydantic backend ». Après M9c-T2 backend, le miroir est correct.

### 6.2 `WorkspaceChunkingTab.schema.ts`

```diff
- export const CHUNKING_STRATEGIES: ChunkingStrategy[] = ["paragraph"];
+ export const CHUNKING_STRATEGIES: ChunkingStrategy[] = ["paragraph", "markdown"];

  export const chunkingFormSchema = z
    .object({
-     strategy: z.enum(["paragraph"]),
+     strategy: z.enum(["paragraph", "markdown"]),
      max_chars: z.coerce.number().int().min(1, "min"),
      min_chars: z.coerce.number().int().min(0, "min"),
      overlap_chars: z.coerce.number().int().min(0, "min"),
    })
    .superRefine(...);  // inchangé
```

Le typage `CHUNKING_STRATEGIES: ChunkingStrategy[]` sert de garde TypeScript : ajouter une valeur à l'enum sans la mettre dans cette constante (ou inversement) est signalé par le compilateur.

`DEFAULT_CHUNKING_FORM` reste inchangé (`strategy: "paragraph"`).

---

## 7. Tests

### 7.1 Helper pur — `frontend/src/lib/__tests__/chunkingExtras.test.ts` (4 tests)

| # | Setup | Attendu |
|---|---|---|
| 1 | `current.strategy='paragraph'`, `nextStrategy='paragraph'`, `current.extras={}` | `{}` |
| 2 | `current.strategy='paragraph'`, `nextStrategy='markdown'`, `current.extras={}` | `{}` |
| 3 | `current.strategy='markdown'`, `nextStrategy='paragraph'`, `current.extras={heading_levels:[1,2]}` | `{}` |
| 4 | `current.strategy='markdown'`, `nextStrategy='markdown'`, `current.extras={heading_levels:[1,3]}` | `{heading_levels:[1,3]}` (référence identique) |

### 7.2 Schema — extension de `WorkspaceChunkingTab.schema.test.ts` (+2 à +3 tests)

- `accepts strategy markdown` : `chunkingFormSchema.parse({...valid, strategy:'markdown'})` ne lève pas.
- `rejects unknown strategy` : `parse({...valid, strategy:'foo'})` lève une `ZodError`.
- `CHUNKING_STRATEGIES order` : `expect(CHUNKING_STRATEGIES).toEqual(["paragraph", "markdown"])`.

Les tests existants pour `paragraph` doivent rester verts (non-régression).

### 7.3 Composant — extension de `WorkspaceChunkingTab.test.tsx` (+4 tests)

| # | Test | Setup mock | Assertion |
|---|---|---|---|
| 1 | `Select renders both strategies` | `mockState(mockConfig)` (paragraph) | Ouvrir le Select trouve `Paragraphes (par défaut)` ET `Markdown` |
| 2 | `Helper text updates when markdown selected` | `mockState(mockConfig)` | Sélectionner markdown → helper text contient « Respecte la structure d'un document Markdown » |
| 3 | `Submit sends extras:{} when switching paragraph → markdown` | `mockState(mockConfig)` (extras={}) | Changer strategy → markdown → Save → `upsertMutate` reçoit `payload.extras === {}` |
| 4 | `Submit preserves admin extras when strategy unchanged on markdown config` | `mockState({...mockConfig, strategy:'markdown', extras:{heading_levels:[1,3]}})` | Éditer `max_chars` seul → Save → `upsertMutate` reçoit `payload.extras === {heading_levels:[1,3]}` |

**Pattern Radix Select dans jsdom** : le composant `Select` de shadcn (Radix UI) ne s'ouvre pas avec un `click` synthétique simple. Pattern à utiliser : `userEvent.click` (déjà disponible dans le projet) ou `fireEvent.pointerDown` sur le trigger. Si Radix Select pose problème en jsdom (limite connue sur certaines versions), fallback de test : invoquer `Controller.onChange` directement plutôt que la UI Select. Décision finale à l'implémentation selon le comportement observé.

### 7.4 Non-régression

- `npm test` : toutes les suites Vitest restent vertes (notamment `WorkspaceChunkingTab.test.tsx` existant, `WorkspaceChunkingTab.schema.test.ts`, `useChunking.test.tsx`).
- `npx tsc --noEmit` : clean. Un usage non-exhaustif de `ChunkingStrategy` (switch sans default) serait signalé — il n'y en a pas dans le code actuel (le composant utilise des accès par clé `t(\`chunking.fields.strategies.${s}\`)` et `t(\`chunking.fields.strategyHelp.${form.watch("strategy")}\`)`, qui s'élargissent transparentement).
- `npm run lint` + `npm run format` : clean.

### 7.5 Pas de test backend

M9c backend déjà livré et testé. Contrat API inchangé. Aucun nouveau test backend nécessaire.

---

## 8. Plan de livraison et numérotation

- **M9c-front** = ce jalon (frontend markdown chunker exposé).

Découpage des tâches au plan d'implémentation (rédigé après validation de cette spec) :

1. Type + Zod enum élargis (`chunking.types.ts` + `WorkspaceChunkingTab.schema.ts`) + tests schema (`schema.test.ts`)
2. Helper `computeExtrasPayload` + tests purs (`chunkingExtras.ts` + `chunkingExtras.test.ts`)
3. Intégration helper dans `WorkspaceChunkingTab.tsx` + i18n FR/EN + tests composant (`WorkspaceChunkingTab.test.tsx`)
4. Roadmap : marquer M9c-front livré ; smoke final (`npm test`, `npx tsc --noEmit`, `npm run lint`, `npm run dev` + check manuel onglet Chunking)

---

## 9. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| Radix Select récalcitrant en jsdom | Fallback documenté §7.3 : invoquer `Controller.onChange` directement |
| Régression silencieuse de `heading_levels` custom d'un admin | Helper `computeExtrasPayload` testé sur le cas 4 (matrice §4.3) |
| Workspace existant en `strategy='markdown'` au moment du déploiement front | Avant M9c-front, `form.reset` accepte `markdown` (pas de validation au reset) mais le Select shadcn n'a pas d'item correspondant → affiche la valeur brute, sans helper text traduit, et toute édition d'un autre champ déclenche un échec Zod au submit. Après M9c-front, l'option apparaît dans le Select, le helper est traduit, et le submit passe. Pas de migration de données nécessaire |
| Différence FR/EN de helper text (mauvaise traduction) | Revue lecture des deux helpers dans la spec §5. Pas de génération auto |
| Tests existants utilisant `mockConfig.strategy='paragraph'` deviennent incomplets | Les nouveaux tests §7.3 ajoutent explicitement la couverture markdown. Pas de modification rétroactive |

---

## 10. Hors-scope explicite

- **Édition de `heading_levels` côté IHM** : reste pilotable uniquement via API admin (`PUT /chunking-config`). Si un besoin produit émerge plus tard, jalon dédié avec son design (multi-select / chips / segmented control, validation Zod miroir de la validation Pydantic).
- **Preview du chunking côté IHM** : reporté. Demanderait un nouveau endpoint backend (`POST /preview-chunking` avec sample text → liste de chunks).
- **Modification backend** : aucune. M9c-T2 a déjà étendu `Literal["paragraph","markdown"]`, M9c-T3/T4/T5 a livré le chunker et la factory.
- **Code chunker (`strategy="code"`)** : jalon ultérieur (M9d ou +).
- **Exposition `metadata` via MCP `search()`** : non couvert (reste cohérent avec le hors-scope M9c backend).
