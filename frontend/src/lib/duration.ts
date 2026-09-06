/** Formatage compact d'une durée de job (index_jobs.duration_ms).
 *  null (job pending/running ou rejet sans job) → "—". */
export function formatDurationMs(ms: number | null): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${Math.round(ms)} ms`;
  const s = ms / 1000;
  if (s < 60) return `${s.toFixed(1)} s`;
  const min = Math.floor(s / 60);
  const rest = Math.round(s % 60);
  return `${min} min ${String(rest).padStart(2, "0")} s`;
}
