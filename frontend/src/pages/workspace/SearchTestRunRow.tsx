import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";

import type { TestRun, TestRunResult } from "@/lib/search-test";

const pct = (v: number) => `${Math.round(v * 100)} %`;

const familyClass: Record<string, string> = {
  litterale: "bg-sky-50 text-sky-700",
  paraphrasee: "bg-violet-50 text-violet-700",
  indirecte: "bg-amber-50 text-amber-700",
  libre: "bg-slate-100 text-slate-600",
};

interface RunRowProps {
  run: TestRun;
  workspaceName: string;
  isOpen: boolean;
  detail: TestRun | undefined;
  onToggle: () => void;
}

/** Une campagne de l'historique : métriques agrégées, puis — déplié — le
 * résultat individuel de chaque question avec ce qui était attendu et ce qui
 * est revenu (top-k, scores), pour l'analyse. */
export function SearchTestRunRow({ run, workspaceName, isOpen, detail, onToggle }: RunRowProps) {
  const { t } = useTranslation("workspace");
  const m = run.metrics;
  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm hover:bg-slate-50"
      >
        <span className="text-xs text-slate-500">{new Date(run.started_at).toLocaleString()}</span>
        <span
          className={`rounded px-1.5 py-0.5 text-xs font-medium ${
            run.config.hybrid ? "bg-emerald-50 text-emerald-700" : "bg-slate-100 text-slate-600"
          }`}
        >
          {run.config.hybrid ? t("search_test.cfg_hybrid") : t("search_test.cfg_vector")}
        </span>
        <span className="font-mono text-xs text-slate-700">
          R@1 {pct(m["recall@1"])} · R@5 {pct(m["recall@5"])} · R@10 {pct(m["recall@10"])} · MRR{" "}
          {m.mrr.toFixed(2)}
        </span>
        <span
          className={`text-xs ${run.questions_failed > 0 ? "text-rose-600" : "text-emerald-700"}`}
        >
          {t("search_test.failed_count", {
            failed: run.questions_failed,
            total: run.questions_total,
          })}
        </span>
      </button>
      {isOpen && (
        <div className="space-y-2 border-t border-slate-100 bg-slate-50 px-3 py-2 text-xs">
          <div className="space-y-0.5">
            {Object.entries(m.families).map(([family, fm]) => (
              <p key={family} className="font-mono text-slate-600">
                {family} : R@5 {pct(fm["recall@5"])} · MRR {fm.mrr.toFixed(2)}
              </p>
            ))}
          </div>
          {(detail?.results ?? []).map((r) => (
            <ResultRow key={r.question} result={r} workspaceName={workspaceName} />
          ))}
        </div>
      )}
    </div>
  );
}

/** Un résultat de question — déplié : attendu, erreur éventuelle, top-k
 * retourné avec scores (le hit attendu est surligné). */
function ResultRow({ result, workspaceName }: { result: TestRunResult; workspaceName: string }) {
  const { t } = useTranslation("workspace");
  const [open, setOpen] = useState(false);

  const verdict = result.error
    ? { label: t("search_test.error_badge"), cls: "bg-amber-50 text-amber-700" }
    : result.rank === null
      ? { label: t("search_test.absent_badge"), cls: "bg-rose-50 text-rose-700" }
      : {
          label: t("search_test.rank_badge", { rank: result.rank }),
          cls: "bg-emerald-50 text-emerald-700",
        };

  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-2 px-2 py-1.5 text-left hover:bg-slate-50"
      >
        <span
          className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${familyClass[result.family] ?? familyClass.libre}`}
        >
          {result.family}
        </span>
        <span className="min-w-0 flex-1 truncate text-slate-700" title={result.question}>
          {result.question}
        </span>
        <span className={`shrink-0 rounded px-1.5 py-0.5 font-medium ${verdict.cls}`}>
          {verdict.label}
        </span>
      </button>
      {open && (
        <div className="space-y-1.5 border-t border-slate-100 px-2 py-1.5">
          <p className="text-slate-500">
            {t("search_test.expected_label")}{" "}
            <Link
              to={`/workspaces?ws=${encodeURIComponent(workspaceName)}&tab=index&doc=${encodeURIComponent(result.expected_path_contains)}`}
              className="font-mono text-sky-700 underline-offset-2 hover:underline"
            >
              {result.expected_path_contains}
            </Link>
          </p>
          {result.error && (
            <p className="text-amber-700">
              {t("search_test.error_label")} <span className="font-mono">{result.error}</span>
            </p>
          )}
          {result.returned.length === 0 ? (
            !result.error && <p className="text-slate-400">{t("search_test.returned_empty")}</p>
          ) : (
            <div>
              <p className="mb-1 text-slate-500">
                {t("search_test.returned_title", { count: result.returned.length })}
              </p>
              <ol className="space-y-0.5">
                {result.returned.map((h) => (
                  <li
                    key={`${h.path}-${h.chunk_index}-${h.rank}`}
                    className={`rounded px-1.5 py-1 ${h.matched ? "bg-emerald-50" : ""}`}
                    title={h.snippet}
                  >
                    <span className="font-mono text-slate-400">{h.rank}.</span>{" "}
                    <span
                      className={`break-all font-mono ${h.matched ? "font-semibold text-emerald-800" : "text-slate-600"}`}
                    >
                      {h.path}
                    </span>{" "}
                    <span className="font-mono text-slate-400">{h.score.toFixed(3)}</span>
                    {h.snippet && (
                      <span className="mt-0.5 block truncate text-slate-400">{h.snippet}</span>
                    )}
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
