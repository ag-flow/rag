# `relativeTime` — Helper partagé pour timestamps relatifs

> **Statut** : design validé pour implémentation.
> **Motivation** : éliminer la duplication du helper `relativeTimeRaw` (et de son pattern de localisation) dans 6 fichiers du dossier `frontend/src/pages/workspace/`. Dette identifiée pendant la review M9c-front (commit `c923fe4`).
> **Hors-scope explicite** : pas de hook réactif (refresh chaque minute), pas de changement i18n, pas de changement backend.

---

## 1. Contexte et motivation

Le helper `relativeTimeRaw` (calcule la clé i18n `time.justNow` / `time.minutesAgo` / `time.hoursAgo` / `time.daysAgo` à partir d'un timestamp ISO) est **dupliqué** dans 6 fichiers :

- `WorkspaceChunkingTab.tsx` (signature `string`)
- `WorkspaceRerankTab.tsx` (signature `string`)
- `WorkspaceHeader.tsx` (signature `string`)
- `WorkspaceSourcesTab.tsx` (signature `string | null`)
- `WorkspaceDetailTab.tsx` (signature `string | null`)
- `WorkspaceJobsTab.tsx` (signature `string | null`)

De plus, **chaque** call-site duplique la ternaire de localisation :

```typescript
rt.key === "time.justNow" ? t("time.justNow") : t(rt.key, { count: rt.count })
```

Ce pattern est répété 6 fois en plus du helper lui-même.

**Impact pratique** : `WorkspaceChunkingTab.tsx` est à 320 lignes (au-dessus du seuil 300 défini par CLAUDE.md). Cette duplication contribue à la pression sur la taille des fichiers et à la dette de maintenance (toute évolution du format temps doit toucher 6 endroits).

---

## 2. Décisions de design

| # | Décision | Justification |
|---|---|---|
| D1 | Deux fonctions exportées : `relativeTimeKey(iso)` (pure, retourne `{key, count}`) + `formatRelativeTime(iso, t)` (retourne la string traduite) | Sépare la logique de calcul (testable sans i18n) de la composition avec `t`. Élimine à la fois la duplication du helper ET de la ternaire de localisation |
| D2 | `iso: string` non-null dans les deux signatures | Callers nullable (3 sur 6) gèrent leur fallback explicitement. Évite de forcer un fallback param ou de retourner `string \| null`. Les 3 callers nullable ont des fallbacks distincts (`"—"`, `t("sources.neverSynced")`, `"—"`), preuve que la décision doit rester côté caller |
| D3 | Type `TranslateFn` local minimal au lieu de `TFunction` de i18next | Découple le helper du typage i18n complexe (génériques par namespace). Compatible structurellement avec `t` de `useTranslation()`. Testable avec un simple `vi.fn()` |
| D4 | `formatRelativeTime` conserve la ternaire `key === "time.justNow"` pour ne pas passer `count` inutilement | La clé `time.justNow` n'a pas d'interpolation `{{count}}` (vérifié dans `fr/workspace.json:246`). Passer `count` à `t()` fonctionnerait mais est moins propre |
| D5 | Pas de hook réactif `useRelativeTime` (refresh chaque minute) | YAGNI. Aucun besoin UX exprimé. Garde l'API simple. Pourra être ajouté en jalon dédié si nécessaire |
| D6 | Pas de gestion explicite des `iso` dans le futur (clock skew) | `diffMs < 0` produit `m < 1` → "à l'instant" gracieusement. Cas rare, comportement acceptable |
| D7 | Fichier dédié `lib/relativeTime.ts` (pas `lib/time.ts` générique) | Une seule responsabilité claire. Symétrique aux helpers existants (`lib/chunkingExtras.ts`, etc.). Évite le risque "grab-bag" d'un fichier `time.ts` |
| D8 | Migration en 2 étapes (non-nullable d'abord, nullable ensuite) | Limite le risque de régression. Les call-sites non-nullable sont triviaux ; les nullable demandent l'inlining de la branche `if (!iso)` |

---

## 3. Inventaire des fichiers

### 3.1 Fichiers à créer

| Fichier | Responsabilité |
|---|---|
| `frontend/src/lib/relativeTime.ts` | 2 fonctions exportées + type `TranslateFn` local |
| `frontend/src/lib/__tests__/relativeTime.test.ts` | 10 tests purs (7 sur `relativeTimeKey`, 3 sur `formatRelativeTime`) |

### 3.2 Fichiers à modifier

| Fichier | Modification | Lignes économisées (estimation) |
|---|---|---|
| `frontend/src/pages/workspace/WorkspaceChunkingTab.tsx` | Supprime helper local (9 lignes) + simplifie IIFE en appel direct | ~12 |
| `frontend/src/pages/workspace/WorkspaceRerankTab.tsx` | Idem | ~12 |
| `frontend/src/pages/workspace/WorkspaceHeader.tsx` | Idem | ~12 |
| `frontend/src/pages/workspace/WorkspaceSourcesTab.tsx` | Supprime helper local nullable + inline `iso ? format(iso, t) : t("sources.neverSynced")` | ~10 |
| `frontend/src/pages/workspace/WorkspaceDetailTab.tsx` | Supprime helper local nullable + inline `iso ? format(iso, t) : "—"` (dans `t("detail.stats.lastIndexed", { when })`) | ~10 |
| `frontend/src/pages/workspace/WorkspaceJobsTab.tsx` | Supprime helper local nullable + inline `iso ? format(iso, t) : "—"` | ~10 |

**Total estimé** : ~60 lignes net supprimées sur l'ensemble. `WorkspaceChunkingTab.tsx` passe de 320 à ~308 lignes (toujours au-dessus du seuil 300 mais nette amélioration).

### 3.3 Fichiers non touchés

- `frontend/src/i18n/fr/workspace.json` et `en/workspace.json` : les 4 clés `time.*` restent inchangées.
- Aucun fichier backend.
- Aucun test existant n'utilise `relativeTimeRaw` directement (la fonction est privée à chaque module) → pas de mise à jour de tests existants.

---

## 4. Module `lib/relativeTime.ts`

### 4.1 Code complet

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

### 4.2 Notes de typage

- `TranslateFn` exporté ? **Non** — type interne au module. Si un caller veut typer son propre `t`, il utilise directement le type de retour de `useTranslation()`.
- Pas d'overload : si un caller a `iso: string | null`, il fait `iso ? formatRelativeTime(iso, t) : fallback` côté caller (décision D2).
- Le retour de `relativeTimeKey` n'est pas un type exporté nommé (juste `{ key: string; count: number }` inline). Les callers n'ont pas besoin de manipuler cette shape directement (ils utilisent `formatRelativeTime`).

---

## 5. Tests

### 5.1 Fichier `frontend/src/lib/__tests__/relativeTime.test.ts`

10 tests purs avec `vi.useFakeTimers()` + `vi.setSystemTime()` pour fixer "maintenant".

**Tests `relativeTimeKey` (7 tests)** :

| # | Setup (iso - now) | Attendu |
|---|---|---|
| 1 | exactement now (diff = 0 ms) | `{ key: "time.justNow", count: 0 }` |
| 2 | 30 secondes avant | `{ key: "time.justNow", count: 0 }` |
| 3 | 1 minute exactement (60 000 ms) | `{ key: "time.minutesAgo", count: 1 }` |
| 4 | 59 minutes avant | `{ key: "time.minutesAgo", count: 59 }` |
| 5 | 1 heure exactement | `{ key: "time.hoursAgo", count: 1 }` |
| 6 | 23 heures avant | `{ key: "time.hoursAgo", count: 23 }` |
| 7 | 1 jour exactement | `{ key: "time.daysAgo", count: 1 }` |

Couvre les 4 branches + 3 frontières (seuils 1min, 1h, 1j).

**Tests `formatRelativeTime` (3 tests)** :

| # | Setup | Attendu |
|---|---|---|
| 1 | iso = now | `t("time.justNow")` appelé **sans** options ; retourne le résultat de `t` |
| 2 | iso = 30 minutes avant | `t("time.minutesAgo", { count: 30 })` appelé ; retourne le résultat |
| 3 | iso = 5 jours avant | `t("time.daysAgo", { count: 5 })` appelé ; retourne le résultat |

Pattern type :

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

  it("< 1 minute → time.justNow", () => {
    expect(relativeTimeKey(isoAgo(30_000))).toEqual({
      key: "time.justNow",
      count: 0,
    });
  });
  // ... 6 autres cas
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

  it("appelle t avec count pour minutesAgo", () => {
    const t = vi.fn((key: string, opts?: { count: number }) =>
      opts ? `[${key} ${opts.count}]` : `[${key}]`,
    );
    const result = formatRelativeTime(isoAgo(30 * 60_000), t);
    expect(t).toHaveBeenCalledWith("time.minutesAgo", { count: 30 });
    expect(result).toBe("[time.minutesAgo 30]");
  });
  // ... 1 test pour daysAgo
});
```

### 5.2 Non-régression

Aucun test des 6 fichiers workspace touchés n'utilise `relativeTimeRaw` directement (la fonction est privée à chaque module). Les tests existants exercent le rendu final via RTL. Tant que la string traduite reste identique à la précédente, ils restent verts.

`npm run test:run` : 159 + 10 = 169 tests verts attendus après livraison.

---

## 6. Migration des 6 call-sites

### 6.1 Call-sites non-nullable (3 fichiers — Tâche 2 du plan)

#### `WorkspaceChunkingTab.tsx` (320 → ~308 lignes)

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
+ import { formatRelativeTime } from "@/lib/relativeTime";

  // dans le JSX (lignes ~253-258 actuelles) :
- {(() => {
-   const rt = relativeTimeRaw(data.updated_at);
-   const when =
-     rt.key === "time.justNow" ? t("time.justNow") : t(rt.key, { count: rt.count });
-   return t("chunking.lastModified", { when });
- })()}
+ {t("chunking.lastModified", {
+   when: formatRelativeTime(data.updated_at, t),
+ })}
```

#### `WorkspaceRerankTab.tsx` (symétrique, clé `rerank.lastModified`)

#### `WorkspaceHeader.tsx` (champ `workspace.created_at`, clé `header.created`)

### 6.2 Call-sites nullable (3 fichiers — Tâche 3 du plan)

#### `WorkspaceSourcesTab.tsx`

```diff
- function relativeTimeRaw(iso: string | null): { key: string; count: number } | null {
-   if (!iso) return null;
-   const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
-   …
- }
+ import { formatRelativeTime } from "@/lib/relativeTime";

  // dans le JSX :
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

#### `WorkspaceDetailTab.tsx` (fallback `"—"`, intégré dans `t("detail.stats.lastIndexed", { when })`)

```diff
- {(() => {
-   const rel = relativeTimeRaw(workspace.last_indexed_at);
-   const when = !rel
-     ? "—"
-     : rel.key === "time.justNow" ? t("time.justNow") : t(rel.key, { count: rel.count });
-   return t("detail.stats.lastIndexed", { when });
- })()}
+ {t("detail.stats.lastIndexed", {
+   when: workspace.last_indexed_at
+     ? formatRelativeTime(workspace.last_indexed_at, t)
+     : "—",
+ })}
```

#### `WorkspaceJobsTab.tsx`

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

---

## 7. Plan de livraison et numérotation

- **T1** : Créer `lib/relativeTime.ts` + `lib/__tests__/relativeTime.test.ts` (10 tests) en TDD strict (rouge → vert → commit).
- **T2** : Migrer les 3 call-sites non-nullable (`WorkspaceChunkingTab`, `WorkspaceRerankTab`, `WorkspaceHeader`). Un seul commit pour les 3 (changement homogène). Smoke `npm run test:run` + `npx tsc --noEmit` après.
- **T3** : Migrer les 3 call-sites nullable (`WorkspaceSourcesTab`, `WorkspaceDetailTab`, `WorkspaceJobsTab`). Un seul commit. Smoke après.
- **T4** : Smoke final (`tsc + lint + test:run`) + vérification que 169 tests passent (159 + 10). Pas de mise à jour roadmap (pas un jalon produit, refactor interne).

Détails au plan d'implémentation rédigé après validation de cette spec.

---

## 8. Risques et points d'attention

| Risque | Mitigation |
|---|---|
| Régression visuelle (string traduite différente) | Le helper extrait produit exactement la même string qu'avant (logique identique, ternaire `justNow` préservée). Tests RTL existants exercent le rendu final |
| `WorkspaceChunkingTab.tsx` reste à ~308 lignes (toujours au-dessus de 300) | Documenté en §3.2. Le vrai fix viendrait d'extraire `handleUpsertResult` ou de scinder les sections du form — hors-scope de ce refactor |
| Import circulaire ou organisation `lib/` | `lib/relativeTime.ts` ne dépend d'aucun autre module du repo. Pas de risque |
| Typing de `t` qui diverge selon les namespaces (`workspace`, `common`) | Le type `TranslateFn` local minimal est compatible structurellement avec n'importe quel `t` retourné par `useTranslation()`. Pas de dépendance à un namespace spécifique |
| Tests RTL des composants migrés cassent | Les 7 tests existants de `WorkspaceChunkingTab.test.tsx` ne testent pas le bloc "Dernière modification" directement. Les autres composants ont aussi peu de tests sur la string temps. Si un test casse, c'est un bug — investiguer plutôt que masquer |

---

## 9. Hors-scope explicite

- **Hook réactif `useRelativeTime(iso)`** : pas de refresh chaque minute. Si "il y a 5 minutes" devient "il y a 6 minutes" sans interaction utilisateur, c'est une amélioration UX qui mérite son propre jalon.
- **Changement i18n** : les 4 clés `time.*` restent inchangées. Aucun pluriel n'est ajouté.
- **Changement backend** : aucun. Le format des ISO retournés par l'API n'est pas modifié.
- **Refactor des IIFE en sous-composants** : on garde les `t("...", { when: ... })` en JSX inline. Pas d'extraction de sous-composants type `<LastModifiedLabel iso={...} />`.
- **Suppression d'autres dettes pré-existantes** : `WorkspaceChunkingTab.tsx` reste au-dessus de 300 lignes après ce refactor. Adressé séparément si besoin.
