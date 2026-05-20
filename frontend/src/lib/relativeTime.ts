/**
 * Type minimal représentant la fonction `t` de react-i18next pour les
 * usages du helper : traduction sans options et traduction avec `count`.
 *
 * Défini en interface callable (pas en `type =`) pour que TypeScript
 * applique la vérification par overload plutôt que par assignabilité
 * structurelle stricte — compatible à la fois avec `TFunction<"workspace">`
 * et avec les mocks Vitest `vi.fn(...)`.
 */
interface TranslateFn {
  (key: string): string;
  (key: string, options: { count: number }): string;
}

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
