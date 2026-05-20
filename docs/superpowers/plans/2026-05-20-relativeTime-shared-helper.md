# `relativeTime` partagé — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extraire le helper `relativeTimeRaw` dupliqué dans 6 fichiers `frontend/src/pages/workspace/` vers un module partagé `lib/relativeTime.ts` avec 2 fonctions (`relativeTimeKey` pure + `formatRelativeTime` i18n), supprimer aussi la ternaire de localisation répétée 6×, et migrer les 6 call-sites.

**Architecture:** Nouveau module `frontend/src/lib/relativeTime.ts` exposant `relativeTimeKey(iso)` (pure, calcule la clé i18n + count) et `formatRelativeTime(iso, t)` (renvoie la string traduite, gère le cas `time.justNow` sans count). Type `TranslateFn` interne minimal pour découpler de i18next. Callers nullable (3 sur 6) gèrent leur fallback inline (`"—"`, `t("sources.neverSynced")`).

**Tech Stack:** TypeScript strict, Vitest avec `vi.useFakeTimers()` + `vi.setSystemTime()` pour les tests purs, react-i18next côté callers (helper indépendant de la lib).

**Spec design** : `docs/superpowers/specs/2026-05-20-relativeTime-shared-helper-design.md`

---

## File Structure

| Fichier | Statut | Responsabilité |
|---|---|---|
| `frontend/src/lib/relativeTime.ts` | **Create** | 2 fonctions exportées + type `TranslateFn` interne |
| `frontend/src/lib/__tests__/relativeTime.test.ts` | **Create** | 10 tests purs (7 sur `relativeTimeKey`, 3 sur `formatRelativeTime`) |
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | **Modify** | Supprime helper local + simplifie IIFE → 1 appel `formatRelativeTime` |
| `frontend/src/pages/workspace/WorkspaceRerankTab.tsx` | **Modify** | Idem |
| `frontend/src/pages/workspace/WorkspaceHeader.tsx` | **Modify** | Idem |
| `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx` | **Modify** | Supprime helper local nullable + inline `iso ? format(iso, t) : t("sources.neverSynced")` |
| `frontend/src/pages/workspace/WorkspaceDetailTab.tsx` | **Modify** | Supprime helper local nullable + inline `iso ? format(iso, t) : "—"` (dans le `when` de `t("detail.stats.lastIndexed", { when })`) |
| `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` | **Modify** | Supprime helper local nullable + inline `iso ? format(iso, t) : "—"` |

Pas de fichier backend touché. Pas de modification i18n. Pas de mise à jour roadmap (refactor interne, pas un jalon produit).

---

## Task 1 — Module `relativeTime.ts` + 10 tests purs

**Files:**
- Create: `frontend/src/lib/relativeTime.ts`
- Create: `frontend/src/lib/__tests__/relativeTime.test.ts`

### Step 1 : Écrire les 10 tests purs (rouge)

Créer `frontend/src/lib/__tests__/relativeTime.test.ts` :

```typescript
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { relativeTimeKey, formatRelativeTime } from "@/lib/relativeTime";

const NOW = new Date("2026-05-20T12:00:00Z").getTime();

function isoAgo(ms: number): string {
  return new Date(NOW - ms).toISOString();
}

describe("relativeTimeKey", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("renvoie time.justNow pour diff = 0", () => {
    expect(relativeTimeKey(isoAgo(0))).toEqual({
      key: "time.justNow",
      count: 0,
    });
  });

  it("renvoie time.justNow pour 30 secondes (< 1 minute)", () => {
    expect(relativeTimeKey(isoAgo(30_000))).toEqual({
      key: "time.justNow",
      count: 0,
    });
  });

  it("renvoie time.minutesAgo pour exactement 1 minute", () => {
    expect(relativeTimeKey(isoAgo(60_000))).toEqual({
      key: "time.minutesAgo",
      count: 1,
    });
  });

  it("renvoie time.minutesAgo pour 59 minutes", () => {
    expect(relativeTimeKey(isoAgo(59 * 60_000))).toEqual({
      key: "time.minutesAgo",
      count: 59,
    });
  });

  it("renvoie time.hoursAgo pour exactement 1 heure", () => {
    expect(relativeTimeKey(isoAgo(60 * 60_000))).toEqual({
      key: "time.hoursAgo",
      count: 1,
    });
  });

  it("renvoie time.hoursAgo pour 23 heures", () => {
    expect(relativeTimeKey(isoAgo(23 * 60 * 60_000))).toEqual({
      key: "time.hoursAgo",
      count: 23,
    });
  });

  it("renvoie time.daysAgo pour exactement 1 jour", () => {
    expect(relativeTimeKey(isoAgo(24 * 60 * 60_000))).toEqual({
      key: "time.daysAgo",
      count: 1,
    });
  });
});

describe("formatRelativeTime", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    vi.setSystemTime(NOW);
  });
  afterEach(() => vi.useRealTimers());

  it("appelle t sans options pour justNow", () => {
    const t = vi.fn((key: string) => `[${key}]`);
    const result = formatRelativeTime(isoAgo(0), t);
    expect(t).toHaveBeenCalledWith("time.justNow");
    expect(t).toHaveBeenCalledTimes(1);
    expect(result).toBe("[time.justNow]");
  });

  it("appelle t avec count pour minutesAgo (30 min)", () => {
    const t = vi.fn((key: string, opts?: { count: number }) =>
      opts ? `[${key} ${opts.count}]` : `[${key}]`,
    );
    const result = formatRelativeTime(isoAgo(30 * 60_000), t);
    expect(t).toHaveBeenCalledWith("time.minutesAgo", { count: 30 });
    expect(result).toBe("[time.minutesAgo 30]");
  });

  it("appelle t avec count pour daysAgo (5 jours)", () => {
    const t = vi.fn((key: string, opts?: { count: number }) =>
      opts ? `[${key} ${opts.count}]` : `[${key}]`,
    );
    const result = formatRelativeTime(isoAgo(5 * 24 * 60 * 60_000), t);
    expect(t).toHaveBeenCalledWith("time.daysAgo", { count: 5 });
    expect(result).toBe("[time.daysAgo 5]");
  });
});
```

### Step 2 : Lancer les tests pour vérifier qu'ils échouent

Run depuis le repo root :

```bash
cd frontend && npm run test:run -- src/lib/__tests__/relativeTime.test.ts
```

Expected : FAIL — le module `@/lib/relativeTime` n'existe pas (`Failed to resolve import` ou équivalent).

### Step 3 : Créer le module `relativeTime.ts`

Créer `frontend/src/lib/relativeTime.ts` :

```typescript
/**
 * Type minimal compatible avec la fonction `t` de react-i18next.
 * Évite la dépendance directe à i18next côté typage du helper.
 */
type TranslateFn = (key: string, options?: { count: number }) => string;

/**
 * Calcule la clé i18n et le compteur pour un timestamp ISO.
 *
 * Retourne :
 * - `{ key: "time.justNow", count: 0 }` si < 1 minute
 * - `{ key: "time.minutesAgo", count: n }` si < 1 heure
 * - `{ key: "time.hoursAgo", count: n }` si < 1 jour
 * - `{ key: "time.daysAgo", count: n }` sinon
 *
 * Pur : ne dépend que de `Date.now()` et de l'argument.
 */
export function relativeTimeKey(iso: string): { key: string; count: number } {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return { key: "time.justNow", count: 0 };
  if (m < 60) return { key: "time.minutesAgo", count: m };
  const h = Math.floor(m / 60);
  if (h < 24) return { key: "time.hoursAgo", count: h };
  return { key: "time.daysAgo", count: Math.floor(h / 24) };
}

/**
 * Formate un timestamp ISO en string relative traduite.
 *
 * Pour `time.justNow`, n'appelle pas `t` avec `count` (la clé n'a pas
 * d'interpolation `{{count}}`). Pour les autres, transmet `count`.
 *
 * @param iso - timestamp ISO non-null. Les callers nullable gèrent leur
 *   fallback explicitement avant l'appel.
 * @param t - fonction de traduction (de useTranslation())
 */
export function formatRelativeTime(iso: string, t: TranslateFn): string {
  const rt = relativeTimeKey(iso);
  return rt.key === "time.justNow"
    ? t("time.justNow")
    : t(rt.key, { count: rt.count });
}
```

**Important — préservation Unicode** : le docstring contient des accents français (`à`, `é`) et le caractère `→` ailleurs. Ne PAS stripper ces caractères (issue rencontrée sur d'autres jalons).

### Step 4 : Relancer les tests, vérifier le vert + tsc

Run :

```bash
cd frontend && npm run test:run -- src/lib/__tests__/relativeTime.test.ts && npx tsc --noEmit
```

Expected :
- Tests : 10 verts (7 `relativeTimeKey` + 3 `formatRelativeTime`).
- `tsc` : 0 erreur.

### Step 5 : Commit

```bash
git add frontend/src/lib/relativeTime.ts frontend/src/lib/__tests__/relativeTime.test.ts
git commit -m "feat(relativeTime-T1): module partage relativeTimeKey + formatRelativeTime + 10 tests purs"
```

---

## Task 2 — Migration des 3 call-sites non-nullable

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceRerankTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceHeader.tsx`

Cette tâche migre les 3 fichiers où `iso` est garanti non-null (`workspace.created_at`, `data.updated_at`). Les 3 changements sont structurellement identiques.

### Step 1 : `WorkspaceChunkingTab.tsx` — supprimer helper local + ajouter import

Modifier `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` :

a) **Supprimer la fonction locale** (lignes ~32-40 actuellement) :

```diff
- function relativeTimeRaw(iso: string): { key: string; count: number } {
-   const diffMs = Date.now() - new Date(iso).getTime();
-   const m = Math.floor(diffMs / 60_000);
-   if (m < 1) return { key: "time.justNow", count: 0 };
-   if (m < 60) return { key: "time.minutesAgo", count: m };
-   const h = Math.floor(m / 60);
-   if (h < 24) return { key: "time.hoursAgo", count: h };
-   return { key: "time.daysAgo", count: Math.floor(h / 24) };
- }
```

b) **Ajouter l'import** (à côté des autres imports `@/lib/...` en haut du fichier) :

```diff
  import { isChunkingChangeRequiresReindex } from "@/lib/chunking";
  import type { UpsertChunkingResult } from "@/lib/chunking";
  import type { ChunkingSpec, ChunkingStrategy } from "@/lib/chunking.types";
  import { computeExtrasPayload } from "@/lib/chunkingExtras";
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) **Simplifier l'IIFE** (lignes ~253-258 actuellement, dans le JSX) :

```diff
  <p className="text-xs text-slate-500">
-   {(() => {
-     const rt = relativeTimeRaw(data.updated_at);
-     const when =
-       rt.key === "time.justNow" ? t("time.justNow") : t(rt.key, { count: rt.count });
-     return t("chunking.lastModified", { when });
-   })()}
+   {t("chunking.lastModified", {
+     when: formatRelativeTime(data.updated_at, t),
+   })}
  </p>
```

### Step 2 : `WorkspaceRerankTab.tsx` — symétrique (clé `rerank.lastModified`)

Modifier `frontend/src/pages/workspace/WorkspaceRerankTab.tsx` :

a) Supprimer `function relativeTimeRaw(iso: string)…` (lignes ~28-36 actuellement).

b) Ajouter l'import à côté des autres imports `@/lib/...` :

```diff
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) Simplifier l'IIFE (lignes ~239-243 actuellement) :

```diff
- {(() => {
-   const rt = relativeTimeRaw(data.updated_at);
-   const when =
-     rt.key === "time.justNow" ? t("time.justNow") : t(rt.key, { count: rt.count });
-   return t("rerank.lastModified", { when });
- })()}
+ {t("rerank.lastModified", {
+   when: formatRelativeTime(data.updated_at, t),
+ })}
```

### Step 3 : `WorkspaceHeader.tsx` — champ `workspace.created_at`, clé `header.created`

Modifier `frontend/src/pages/workspace/WorkspaceHeader.tsx` :

a) Supprimer `function relativeTimeRaw(iso: string)…` (lignes ~21-29 actuellement).

b) Ajouter l'import :

```diff
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) Simplifier l'IIFE (lignes ~39-42 actuellement) :

```diff
- {(() => {
-   const rel = relativeTimeRaw(workspace.created_at);
-   const when =
-     rel.key === "time.justNow" ? t("time.justNow") : t(rel.key, { count: rel.count });
-   return t("header.created", { when });
- })()}
+ {t("header.created", {
+   when: formatRelativeTime(workspace.created_at, t),
+ })}
```

### Step 4 : Vérifier tsc + lint + tests (non-régression)

Run :

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:run
```

Expected :
- `tsc` : 0 erreur.
- Lint : 0 erreur (les 4 warnings shadcn pré-existants restent).
- Tests : 159 + 10 (Task 1) = 169 verts.

**Si un test RTL casse** sur l'un de ces 3 composants : ne pas masquer. Investiguer — le helper extrait DOIT produire la même string que le code supprimé. Vérifier que `Date.now()` n'a pas été mocké dans le test concerné de façon incompatible.

### Step 5 : Commit

```bash
git add frontend/src/pages/workspace/WorkspaceChunkingTab.tsx frontend/src/pages/workspace/WorkspaceRerankTab.tsx frontend/src/pages/workspace/WorkspaceHeader.tsx
git commit -m "refactor(relativeTime-T2): migre 3 call-sites non-nullable (Chunking, Rerank, Header)"
```

---

## Task 3 — Migration des 3 call-sites nullable

**Files:**
- Modify: `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceDetailTab.tsx`
- Modify: `frontend/src/pages/workspace/WorkspaceJobsTab.tsx`

Cette tâche migre les 3 fichiers où `iso` peut être null (`source.last_indexed_at`, `workspace.last_indexed_at`, `job.started_at`). Chaque caller inline son propre fallback.

### Step 1 : `WorkspaceSourcesTab.tsx` — fallback `t("sources.neverSynced")`

Modifier `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx` :

a) Supprimer la fonction locale (lignes ~22-30 actuellement) :

```diff
- function relativeTimeRaw(iso: string | null): { key: string; count: number } | null {
-   if (!iso) return null;
-   const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
-   if (m < 1) return { key: "time.justNow", count: 0 };
-   if (m < 60) return { key: "time.minutesAgo", count: m };
-   const h = Math.floor(m / 60);
-   if (h < 24) return { key: "time.hoursAgo", count: h };
-   return { key: "time.daysAgo", count: Math.floor(h / 24) };
- }
```

b) Ajouter l'import :

```diff
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) Simplifier l'IIFE (lignes ~88-93 actuellement, dans une `map` JSX) :

```diff
- {(() => {
-   const rel = relativeTimeRaw(source.last_indexed_at);
-   if (!rel) return t("sources.neverSynced");
-   return rel.key === "time.justNow"
-     ? t("time.justNow")
-     : t(rel.key, { count: rel.count });
- })()}
+ {source.last_indexed_at
+   ? formatRelativeTime(source.last_indexed_at, t)
+   : t("sources.neverSynced")}
```

### Step 2 : `WorkspaceDetailTab.tsx` — fallback `"—"`, intégré dans `t("detail.stats.lastIndexed", { when })`

Modifier `frontend/src/pages/workspace/WorkspaceDetailTab.tsx` :

a) Supprimer la fonction locale (lignes ~27-35 actuellement).

b) Ajouter l'import :

```diff
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) Simplifier l'IIFE (lignes ~73-80 actuellement) :

```diff
- {(() => {
-   const rel = relativeTimeRaw(workspace.last_indexed_at);
-   const when = !rel
-     ? "—"
-     : rel.key === "time.justNow"
-       ? t("time.justNow")
-       : t(rel.key, { count: rel.count });
-   return t("detail.stats.lastIndexed", { when });
- })()}
+ {t("detail.stats.lastIndexed", {
+   when: workspace.last_indexed_at
+     ? formatRelativeTime(workspace.last_indexed_at, t)
+     : "—",
+ })}
```

### Step 3 : `WorkspaceJobsTab.tsx` — fallback `"—"`

Modifier `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` :

a) Supprimer la fonction locale (lignes ~21-29 actuellement).

b) Ajouter l'import :

```diff
+ import { formatRelativeTime } from "@/lib/relativeTime";
```

c) Simplifier l'IIFE (lignes ~100-105 actuellement) :

```diff
- {(() => {
-   const rel = relativeTimeRaw(job.started_at);
-   if (!rel) return "—";
-   return rel.key === "time.justNow"
-     ? t("time.justNow")
-     : t(rel.key, { count: rel.count });
- })()}
+ {job.started_at ? formatRelativeTime(job.started_at, t) : "—"}
```

### Step 4 : Vérifier tsc + lint + tests (non-régression)

Run :

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:run
```

Expected :
- `tsc` : 0 erreur.
- Lint : 0 erreur, 4 warnings shadcn pré-existants seulement.
- Tests : 169 verts (159 + 10).

### Step 5 : Commit

```bash
git add frontend/src/pages/workspace/WorkspaceSourcesTab.tsx frontend/src/pages/workspace/WorkspaceDetailTab.tsx frontend/src/pages/workspace/WorkspaceJobsTab.tsx
git commit -m "refactor(relativeTime-T3): migre 3 call-sites nullable (Sources, Detail, Jobs)"
```

---

## Task 4 — Smoke final + vérification globale

**Files:**
- Aucun changement de code. Étape de validation uniquement.

### Step 1 : Vérifier qu'il ne reste plus d'occurrence de `relativeTimeRaw`

Run :

```bash
cd /e/srcs/ag-flow.rag && grep -rn "relativeTimeRaw" frontend/src/ 2>&1 | wc -l
```

Expected : `0` (aucune occurrence). Si > 0, lister les fichiers et investiguer pourquoi ils ont été manqués.

### Step 2 : Smoke final — typecheck + lint + tests

Run depuis le repo root :

```bash
cd frontend && npx tsc --noEmit && npm run lint && npm run test:run
```

Expected :
- `tsc` : 0 erreur.
- Lint : 0 erreur, 4 warnings shadcn pré-existants seulement.
- Vitest : **169 tests verts** (159 existants + 10 nouveaux du Task 1).

### Step 3 : Vérifier le delta de lignes économisées

Run :

```bash
git diff --stat 445c288..HEAD -- frontend/src/pages/workspace/ frontend/src/lib/relativeTime.ts frontend/src/lib/__tests__/relativeTime.test.ts
```

Expected : delta net **négatif** sur les 6 fichiers workspace (suppression > ajout), positif sur les 2 nouveaux fichiers. Total net attendu : entre -40 et -60 lignes hors tests, +environ 100 lignes de tests purs.

### Step 4 : Vérifier la taille de `WorkspaceChunkingTab.tsx`

Run :

```bash
wc -l frontend/src/pages/workspace/WorkspaceChunkingTab.tsx
```

Expected : ~308 lignes (était 320 avant T2). Documenté dans la spec §3.2 : reste légèrement au-dessus du seuil 300 mais nette amélioration. Pas d'action supplémentaire dans ce jalon.

### Step 5 : Récap des commits du refactor

Run :

```bash
git log --oneline 445c288..HEAD
```

Expected (du plus récent au plus ancien) :
- `refactor(relativeTime-T3): migre 3 call-sites nullable (Sources, Detail, Jobs)`
- `refactor(relativeTime-T2): migre 3 call-sites non-nullable (Chunking, Rerank, Header)`
- `feat(relativeTime-T1): module partage relativeTimeKey + formatRelativeTime + 10 tests purs`

### Step 6 : Vérification manuelle dans le browser (optionnelle, à la main de l'utilisateur)

Pas obligatoire (les tests RTL exercent déjà le rendu des composants concernés). Si souhaité :

```bash
cd frontend && npm run dev
```

Ouvrir un workspace, vérifier dans chacun des onglets :
- **Chunking** : "Dernière modification : il y a X min" sous le form
- **Rerank** : "Dernière modification : il y a X min" sous le form
- **Sources** : "Jamais synchronisé" ou "il y a X min" sur chaque source
- **Détail** : "Dernière indexation : il y a X min" ou "—"
- **Jobs** : "il y a X min" ou "—" sur chaque job
- **Header** : "Créé il y a X min" en haut du workspace

Killer `npm run dev` (Ctrl+C) après vérification.

---

## Récap couverture spec

| Section spec | Tâche | Statut couverture |
|---|---|---|
| §3.1 fichiers à créer | T1 | Couvert (Step 1, 3) |
| §3.2 6 fichiers à modifier | T2 + T3 | Couvert (T2 = 3 non-nullable, T3 = 3 nullable) |
| §3.3 fichiers non touchés | (aucune action) | Respecté implicitement |
| §4 signatures et code du module | T1 Step 3 | Couvert |
| §5 tests (7+3) | T1 Step 1 | Couvert |
| §6.1 call-sites non-nullable | T2 | Couvert |
| §6.2 call-sites nullable | T3 | Couvert |
| §7 plan de livraison T1→T4 | Plan T1→T4 | Couvert |
| §8 risques | T2 Step 4 (investiguer si régression), T4 Step 4 (taille fichier) | Couvert |
| §9 hors-scope | (rien ajouté) | Respecté |
