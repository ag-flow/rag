# M9c-front — Markdown Chunking dans l'IHM Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer la stratégie `markdown` (livrée M9c backend) dans le Select de l'onglet Chunking côté frontend, avec helper text traduit FR/EN et logique `extras` pass-through pour préserver une config admin custom.

**Architecture:** Élargissement minimal du type `ChunkingStrategy` et de l'enum Zod `chunkingFormSchema`. Extraction d'un helper pur `computeExtrasPayload` dans `lib/chunkingExtras.ts` pour décider du payload `extras` au submit (pass-through si strategy inchangée, `{}` sinon). Aucun changement backend. Pas d'UI pour `heading_levels` (reste pilotable via API admin uniquement).

**Tech Stack:** React 18 + TypeScript strict, Vite, Zod, react-hook-form, TanStack Query, i18next, Vitest + React Testing Library + userEvent.

**Spec design** : `docs/superpowers/specs/2026-05-20-M9c-front-markdown-chunking-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `frontend/src/lib/chunking.types.ts` | **Modify** | `type ChunkingStrategy = "paragraph" \| "markdown"` |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` | **Modify** | `CHUNKING_STRATEGIES = ["paragraph", "markdown"]` + `z.enum(["paragraph", "markdown"])` |
| `frontend/src/lib/chunkingExtras.ts` | **Create** | Helper pur `computeExtrasPayload(nextStrategy, current)` |
| `frontend/src/lib/__tests__/chunkingExtras.test.ts` | **Create** | 4 tests purs du helper |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts` | **Modify** | +3 tests (markdown accepté, enum inconnue rejetée, ordre `CHUNKING_STRATEGIES`) |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | **Modify** | Import + usage `computeExtrasPayload` dans `onSubmit` |
| `frontend/src/i18n/fr/workspace.json` | **Modify** | +`chunking.fields.strategies.markdown` + `chunking.fields.strategyHelp.markdown` |
| `frontend/src/i18n/en/workspace.json` | **Modify** | +`chunking.fields.strategies.markdown` + `chunking.fields.strategyHelp.markdown` |
| `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx` | **Modify** | +4 tests (Select offre 2 options, helper change, submit extras `{}` après changement, pass-through si inchangé) |
| `specs/09-roadmap.md` | **Modify** | Marquer M9c-front livré (retire la puce, ajoute la ligne ✅) |

---

## Task 1 — Type + Zod enum élargis + tests schema

**Files:**
- Modify: `frontend/src/lib/chunking.types.ts:5`
- Modify: `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts:4,8`
- Modify: `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts`

### Step 1 : Écrire les tests schema (rouge)

Ajouter ces 3 tests à la fin de `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts`, à l'intérieur du `describe("chunkingFormSchema", ...)` existant :

```typescript
  it("accepte strategy='markdown'", () => {
    expect(() =>
      chunkingFormSchema.parse({
        strategy: "markdown",
        max_chars: 2000,
        min_chars: 200,
        overlap_chars: 200,
      }),
    ).not.toThrow();
  });

  it("rejette une strategy inconnue", () => {
    const r = chunkingFormSchema.safeParse({
      strategy: "foo",
      max_chars: 2000,
      min_chars: 200,
      overlap_chars: 200,
    });
    expect(r.success).toBe(false);
    if (!r.success) {
      expect(r.error.issues[0]?.path).toContain("strategy");
    }
  });
```

Et ajouter un nouveau `describe` à la fin du fichier :

```typescript
import { CHUNKING_STRATEGIES } from "@/pages/workspace/WorkspaceChunkingTab.schema";

describe("CHUNKING_STRATEGIES", () => {
  it("expose paragraph puis markdown dans cet ordre", () => {
    expect(CHUNKING_STRATEGIES).toEqual(["paragraph", "markdown"]);
  });
});
```

**Important** : l'import `CHUNKING_STRATEGIES` doit être ajouté en haut du fichier, à côté de l'import existant `{ chunkingFormSchema, DEFAULT_CHUNKING_FORM }`.

### Step 2 : Lancer les tests pour vérifier qu'ils échouent

Run :

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts
```

Expected : FAIL — `accepte strategy='markdown'` lève (enum n'accepte que `paragraph`), `CHUNKING_STRATEGIES` n'a qu'un seul élément.

### Step 3 : Élargir le type `ChunkingStrategy`

Modifier `frontend/src/lib/chunking.types.ts` ligne 5 :

```diff
- export type ChunkingStrategy = "paragraph";
+ export type ChunkingStrategy = "paragraph" | "markdown";
```

### Step 4 : Élargir l'enum Zod et `CHUNKING_STRATEGIES`

Modifier `frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts` :

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
```

### Step 5 : Relancer les tests, vérifier le vert + tsc

Run :

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts && npx tsc --noEmit
```

Expected :
- Tests : tous verts (les 7 existants + 3 nouveaux = 10).
- `tsc` : aucune erreur.

### Step 6 : Commit

```bash
git add frontend/src/lib/chunking.types.ts frontend/src/pages/workspace/WorkspaceChunkingTab.schema.ts frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.schema.test.ts
git commit -m "feat(M9c-front-T1): elargit Zod enum et ChunkingStrategy a markdown + 3 tests schema"
```

---

## Task 2 — Helper `computeExtrasPayload` + tests purs

**Files:**
- Create: `frontend/src/lib/chunkingExtras.ts`
- Create: `frontend/src/lib/__tests__/chunkingExtras.test.ts`

### Step 1 : Écrire les tests purs (rouge)

Créer `frontend/src/lib/__tests__/chunkingExtras.test.ts` :

```typescript
import { describe, it, expect } from "vitest";
import { computeExtrasPayload } from "@/lib/chunkingExtras";
import type { ChunkingConfig } from "@/lib/chunking.types";

function makeConfig(overrides: Partial<ChunkingConfig> = {}): ChunkingConfig {
  return {
    workspace_id: "ws-1",
    strategy: "paragraph",
    max_chars: 2000,
    min_chars: 200,
    overlap_chars: 200,
    extras: {},
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    ...overrides,
  };
}

describe("computeExtrasPayload", () => {
  it("renvoie {} quand paragraph reste paragraph", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("paragraph", current)).toEqual({});
  });

  it("renvoie {} en switch paragraph → markdown (backend appliquera son default)", () => {
    const current = makeConfig({ strategy: "paragraph", extras: {} });
    expect(computeExtrasPayload("markdown", current)).toEqual({});
  });

  it("renvoie {} en switch markdown → paragraph (sinon backend rejette)", () => {
    const current = makeConfig({
      strategy: "markdown",
      extras: { heading_levels: [1, 2] },
    });
    expect(computeExtrasPayload("paragraph", current)).toEqual({});
  });

  it("preserve current.extras quand markdown reste markdown (conf admin custom)", () => {
    const current = makeConfig({
      strategy: "markdown",
      extras: { heading_levels: [1, 3] },
    });
    expect(computeExtrasPayload("markdown", current)).toBe(current.extras);
  });
});
```

Note `toBe` (et non `toEqual`) sur le dernier test : on vérifie volontairement l'égalité de référence pour documenter le pass-through.

### Step 2 : Lancer les tests pour vérifier qu'ils échouent

Run :

```bash
cd frontend && npm test -- src/lib/__tests__/chunkingExtras.test.ts
```

Expected : FAIL — le module `@/lib/chunkingExtras` n'existe pas.

### Step 3 : Créer le helper

Créer `frontend/src/lib/chunkingExtras.ts` :

```typescript
import type { ChunkingConfig, ChunkingStrategy } from "@/lib/chunking.types";

/**
 * Calcule le payload `extras` à envoyer au PUT /chunking-config.
 *
 * - Si la strategy change → renvoie {} (le backend applique son default,
 *   notamment {heading_levels:[1,2]} pour markdown).
 * - Si la strategy ne change pas → renvoie current.extras tel quel
 *   (préserve un heading_levels custom posé via API admin).
 */
export function computeExtrasPayload(
  nextStrategy: ChunkingStrategy,
  current: ChunkingConfig,
): Record<string, unknown> {
  return nextStrategy === current.strategy ? current.extras : {};
}
```

### Step 4 : Relancer les tests, vérifier le vert

Run :

```bash
cd frontend && npm test -- src/lib/__tests__/chunkingExtras.test.ts && npx tsc --noEmit
```

Expected :
- Tests : 4 tests verts.
- `tsc` : aucune erreur.

### Step 5 : Commit

```bash
git add frontend/src/lib/chunkingExtras.ts frontend/src/lib/__tests__/chunkingExtras.test.ts
git commit -m "feat(M9c-front-T2): helper computeExtrasPayload pass-through + 4 tests purs"
```

---

## Task 3 — Intégration helper + i18n FR/EN + tests composant

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx:23,91-93`
- Modify: `frontend/src/i18n/fr/workspace.json` (bloc `chunking.fields`)
- Modify: `frontend/src/i18n/en/workspace.json` (bloc `chunking.fields`)
- Modify: `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx`

### Step 1 : Étendre l'i18n FR

Dans `frontend/src/i18n/fr/workspace.json`, modifier le bloc `chunking.fields` :

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

### Step 2 : Étendre l'i18n EN

Dans `frontend/src/i18n/en/workspace.json`, modifier le bloc `chunking.fields` (symétrique) :

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

### Step 3 : Vérifier la syntaxe JSON

Run :

```bash
cd frontend && node -e "JSON.parse(require('fs').readFileSync('src/i18n/fr/workspace.json','utf8')); JSON.parse(require('fs').readFileSync('src/i18n/en/workspace.json','utf8')); console.log('OK')"
```

Expected : `OK` (sinon corriger une virgule manquante).

### Step 4 : Écrire les 4 tests composant (rouge)

Dans `frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx`, ajouter en haut du fichier l'import `userEvent` :

```diff
- import { screen, fireEvent, waitFor } from "@testing-library/react";
+ import { screen, fireEvent, waitFor } from "@testing-library/react";
+ import userEvent from "@testing-library/user-event";
```

Si `@testing-library/user-event` n'est pas installé, l'installer :

```bash
cd frontend && npm install --save-dev @testing-library/user-event
```

Puis ajouter ces 4 tests à la fin du `describe("WorkspaceChunkingTab", ...)` :

```typescript
  it("le Select stratégie propose paragraph ET markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    expect(
      screen.getByRole("option", { name: /Paragraphes \(par défaut\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /^Markdown$/i }),
    ).toBeInTheDocument();
  });

  it("le helper text change quand on sélectionne markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /^Markdown$/i }));
    expect(
      screen.getByText(/Respecte la structure d'un document Markdown/i),
    ).toBeInTheDocument();
  });

  it("submit envoie extras:{} après changement de strategy paragraph → markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig); // strategy: 'paragraph', extras: {}
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /^Markdown$/i }));
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs?.payload?.strategy).toBe("markdown");
    expect(callArgs?.payload?.extras).toEqual({});
  });

  it("submit préserve data.extras quand strategy markdown reste markdown", async () => {
    const adminConfig: ChunkingConfig = {
      ...mockConfig,
      strategy: "markdown",
      extras: { heading_levels: [1, 3] },
    };
    mockState(adminConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs?.payload?.strategy).toBe("markdown");
    expect(callArgs?.payload?.extras).toEqual({ heading_levels: [1, 3] });
  });
```

### Step 5 : Lancer les tests pour vérifier qu'ils échouent

Run :

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx
```

Expected :
- Test 1 (le Select propose paragraph ET markdown) : FAIL si Radix Select ne s'ouvre pas en jsdom, OU FAIL parce que l'option markdown n'existe pas encore (i18n présent mais composant n'utilise pas la liste élargie tant que `CHUNKING_STRATEGIES` n'est pas mis à jour — déjà fait T1, donc le seul échec attendu ici est l'interaction Radix).
- Test 3 et 4 : FAIL parce que `extras: {}` est toujours hardcodé dans `WorkspaceChunkingTab.tsx:92`.

**Si Radix Select ne s'ouvre pas en jsdom** (erreurs du genre "pointer capture not implemented") :

- Vérifier que `setupTests.ts` (ou équivalent vitest setup) polyfille `hasPointerCapture` et `scrollIntoView` :

  ```typescript
  // frontend/src/test-setup.ts (ajouter si absent)
  beforeAll(() => {
    Element.prototype.hasPointerCapture = vi.fn();
    Element.prototype.scrollIntoView = vi.fn();
    Element.prototype.releasePointerCapture = vi.fn();
  });
  ```

  Localiser le fichier setup via `vite.config.ts` (`test.setupFiles`). Ajouter les polyfills sans toucher au reste du fichier.

- Si toujours bloqué après les polyfills, **fallback documenté §7.3 de la spec** : remplacer les tests 1, 2, 3 par des tests qui invoquent directement `Controller.onChange` via une exposition de test (ou via `fireEvent.change` sur l'input caché Radix). Le test 4 ne dépend pas du Select et reste tel quel.

### Step 6 : Brancher `computeExtrasPayload` dans `WorkspaceChunkingTab.tsx`

Modifier `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` :

Ajouter l'import en haut du fichier (à côté des autres imports `@/lib/...`) :

```diff
  import { isChunkingChangeRequiresReindex } from "@/lib/chunking";
  import type { UpsertChunkingResult } from "@/lib/chunking";
  import type { ChunkingSpec, ChunkingStrategy } from "@/lib/chunking.types";
+ import { computeExtrasPayload } from "@/lib/chunkingExtras";
```

Puis modifier `onSubmit` (ligne ~91) :

```diff
  const onSubmit = (values: ChunkingFormValues) => {
-   const payload: ChunkingSpec = { ...values, extras: {} };
+   const payload: ChunkingSpec = {
+     ...values,
+     extras: computeExtrasPayload(values.strategy, data),
+   };
    upsert.mutate(
      { payload, confirm: false },
      ...
```

`data` est garanti non-undefined ici (`if (isLoading || !data) return <LoadingSpinner />` plus haut bloque le rendu sinon).

### Step 7 : Relancer les tests, vérifier le vert

Run :

```bash
cd frontend && npm test -- src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx && npx tsc --noEmit
```

Expected :
- Tests : 11 verts au total (7 existants + 4 nouveaux).
- `tsc` : aucune erreur.

### Step 8 : Vérifier non-régression toute suite

Run :

```bash
cd frontend && npm test && npm run lint
```

Expected :
- Toutes les suites Vitest vertes.
- Lint : aucune erreur ni warning.

### Step 9 : Commit

```bash
git add frontend/src/pages/workspace/WorkspaceChunkingTab.tsx frontend/src/i18n/fr/workspace.json frontend/src/i18n/en/workspace.json frontend/src/pages/workspace/__tests__/WorkspaceChunkingTab.test.tsx
# Si le setup test a été modifié pour les polyfills Radix
git add frontend/src/test-setup.ts 2>/dev/null || true
# Si user-event a été installé
git add frontend/package.json frontend/package-lock.json 2>/dev/null || true
git commit -m "feat(M9c-front-T3): expose markdown dans Select Chunking + i18n FR/EN + 4 tests composant"
```

---

## Task 4 — Roadmap + smoke final

**Files:**
- Modify: `specs/09-roadmap.md`

### Step 1 : Mettre à jour la roadmap

Modifier `specs/09-roadmap.md`. Localiser le bloc :

```
✅ Stratégie sémantique `markdown` livrée en M9c — cf. `docs/superpowers/specs/2026-05-19-M9c-backend-markdown-chunker-design.md`. Configurable via API admin (`PUT /chunking-config` avec `strategy='markdown'` + `extras={heading_levels:[1,2]}`). Frontend différé en M9c-front (l'option n'apparaît pas encore dans le Select de l'IHM).

Stratégies disponibles : `paragraph` (M4a), `markdown` (M9c).

Stratégies futures (jalons distincts) :
- M9c-front : exposer `markdown` dans l'IHM workspace
- Chunking par blocs de code (langage-aware) — jalon M9d ou +
```

Et le remplacer par :

```
✅ Stratégie sémantique `markdown` livrée en M9c (backend) + M9c-front (IHM) — cf. `docs/superpowers/specs/2026-05-19-M9c-backend-markdown-chunker-design.md` et `docs/superpowers/specs/2026-05-20-M9c-front-markdown-chunking-design.md`. Configurable via le Select Stratégie de l'onglet Chunking du workspace. Par défaut : `heading_levels=[1,2]` ; customisable via API admin (`PUT /chunking-config` avec `extras.heading_levels=[…]`).

Stratégies disponibles : `paragraph` (M4a), `markdown` (M9c + M9c-front).

Stratégies futures (jalons distincts) :
- Chunking par blocs de code (langage-aware) — jalon M9d ou +
```

### Step 2 : Smoke final — typecheck + lint + format + tests + dev server

Run :

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run format && npm test
```

Expected :
- `tsc` : 0 erreur.
- Lint : 0 erreur, 0 warning.
- Format : aucun fichier modifié (sinon les ré-ajouter au commit).
- Vitest : 100 % vert.

### Step 3 : Vérification manuelle dans le navigateur

Démarrer le dev server :

```bash
cd frontend && npm run dev
```

Ouvrir `http://localhost:5173`, se connecter, sélectionner un workspace existant, ouvrir l'onglet **Chunking**. Vérifier dans cet ordre :

1. Le Select **Stratégie** affiche deux options : « Paragraphes (par défaut) » et « Markdown ».
2. Sélectionner « Markdown » → le helper text en dessous change pour le texte M9c-front (« Respecte la structure d'un document Markdown… »).
3. Cliquer **Enregistrer** → dialog 409 « Réindexation requise » apparaît (si le workspace contient des documents indexés) ou toast succès direct sinon.
4. Confirmer la réindexation → toast « Réindexation lancée », form reset.
5. Revenir sur l'onglet Chunking, vérifier que le Select affiche bien « Markdown » (config persistée).
6. Re-sélectionner « Paragraphes (par défaut) » → helper text revient au texte paragraph.
7. Bouton **Enregistrer** désactivé tant que le form est clean.
8. Pas d'erreur console (F12 → Console). Pas de warning React.

Killer `npm run dev` (Ctrl+C) après vérification.

### Step 4 : Vérifier le smoke côté backend (config persistée correctement)

Récupérer le mot de passe Postgres du LXC de test (cf. memory `secrets-test-location.md`) puis :

```bash
cd backend && uv run python -c "
import asyncio, asyncpg
async def main():
    pool = await asyncpg.create_pool('postgresql://rag:<PASSWORD>@<LXC_IP>:5432/<DB_DU_WORKSPACE>')
    row = await pool.fetchrow('SELECT strategy, extras FROM chunking_configs LIMIT 1')
    print('strategy:', row['strategy'])
    print('extras:', row['extras'])
    await pool.close()
asyncio.run(main())
"
```

Expected : si la stratégie a été passée à markdown via l'IHM, `strategy='markdown'` et `extras` contient `{"heading_levels":[1,2]}` (normalisé par le backend).

Si l'utilisateur n'a pas d'environnement test à portée immédiate, sauter cette étape : la vérification visuelle §3 + les tests Vitest sont suffisants pour valider le contrat.

### Step 5 : Commit final + roadmap

```bash
git add specs/09-roadmap.md
git commit -m "docs(M9c-front-T4): roadmap marque M9c-front livre (markdown expose dans l'IHM)"
```

### Step 6 : Récap des commits du jalon

Run :

```bash
git log --oneline -5
```

Expected (du plus récent au plus ancien) :
- `docs(M9c-front-T4): roadmap marque M9c-front livre …`
- `feat(M9c-front-T3): expose markdown dans Select Chunking + i18n FR/EN + 4 tests composant`
- `feat(M9c-front-T2): helper computeExtrasPayload pass-through + 4 tests purs`
- `feat(M9c-front-T1): elargit Zod enum et ChunkingStrategy a markdown + 3 tests schema`
- `docs(M9c-front): spec exposer markdown dans l'IHM Chunking`

---

## Récap couverture spec

| Section spec | Tâche | Statut couverture |
|---|---|---|
| §3.1 types/Zod | T1 | Couvert (Step 3, 4) |
| §3.1 i18n FR/EN | T3 | Couvert (Step 1, 2) |
| §3.1 onSubmit pass-through | T3 | Couvert (Step 6) |
| §3.1 roadmap | T4 | Couvert (Step 1) |
| §3.2 helper + tests | T2 | Couvert (Step 1-4) |
| §3.2 schema tests +3 | T1 | Couvert (Step 1) |
| §3.2 component tests +4 | T3 | Couvert (Step 4) |
| §4 helper algo | T2 | Couvert |
| §5 i18n changements | T3 | Couvert |
| §6 schéma Zod | T1 | Couvert |
| §7 tests | T1, T2, T3 | Couvert |
| §8 ordre des tâches | Plan T1→T4 | Couvert |
| §9 risques (Radix jsdom) | T3 Step 5 | Couvert (fallback documenté) |
