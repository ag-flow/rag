import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useToast } from "@/hooks/useToast";
import {
  useDeleteQuestion,
  useRunCampaign,
  useSetQuestionEnabled,
  useTestQuestions,
  useTestRunDetail,
  useTestRuns,
} from "@/hooks/useSearchTest";
import { SearchTestRunRow } from "@/pages/workspace/SearchTestRunRow";

interface Props {
  workspaceName: string;
  enabled: boolean;
}

const familyClass: Record<string, string> = {
  litterale: "bg-sky-50 text-sky-700",
  paraphrasee: "bg-violet-50 text-violet-700",
  indirecte: "bg-amber-50 text-amber-700",
  libre: "bg-slate-100 text-slate-600",
};

/** Banc de test de recherche (feature 1a9b8b67) : questions poussées par les
 * agents via MCP, campagne lancée ICI, résultats consultables sur cette page. */
export function WorkspaceSearchTestTab({ workspaceName, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data: questions = [], isLoading } = useTestQuestions(workspaceName, enabled);
  const { data: runs = [] } = useTestRuns(workspaceName, enabled);
  const setEnabledMut = useSetQuestionEnabled(workspaceName);
  const del = useDeleteQuestion(workspaceName);
  const runCampaign = useRunCampaign(workspaceName);
  const [openRunId, setOpenRunId] = useState<string | null>(null);
  const { data: runDetail } = useTestRunDetail(workspaceName, openRunId);

  if (isLoading) return <LoadingSpinner />;

  const activeCount = questions.filter((q) => q.enabled).length;

  const launch = () =>
    runCampaign.mutate(undefined, {
      onSuccess: (run) => {
        setOpenRunId(run.id);
        toast({ title: t("search_test.run_done", { failed: run.questions_failed }) });
      },
      onError: () => toast({ title: t("search_test.run_error"), variant: "destructive" }),
    });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-4">
        <div>
          <h3 className="text-sm font-semibold text-slate-900">
            {t("search_test.title", { count: questions.length })}
          </h3>
          <p className="mt-1 text-xs text-slate-500">{t("search_test.intro")}</p>
        </div>
        <Button onClick={launch} disabled={activeCount === 0 || runCampaign.isPending}>
          {runCampaign.isPending ? t("search_test.running") : t("search_test.run_btn")}
        </Button>
      </div>

      {questions.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("search_test.empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {questions.map((q) => (
            <div
              key={q.id}
              className="flex items-center gap-2 rounded border border-slate-200 bg-white px-3 py-2 text-sm"
            >
              <span
                className={`rounded px-1.5 py-0.5 text-xs font-medium shrink-0 ${familyClass[q.family] ?? familyClass.libre}`}
              >
                {q.family}
              </span>
              <span className="min-w-0 flex-1 truncate" title={q.question}>
                {q.question}
              </span>
              <code className="shrink-0 font-mono text-xs text-slate-400">
                {q.expected_path_contains}
              </code>
              <Switch
                checked={q.enabled}
                onCheckedChange={(on) => setEnabledMut.mutate({ id: q.id, enabled: on })}
                aria-label={t("search_test.toggle_aria")}
              />
              <button
                type="button"
                onClick={() => del.mutate(q.id)}
                className="text-slate-400 hover:text-rose-600"
                aria-label={t("search_test.delete_aria")}
              >
                <Trash2 className="h-4 w-4" />
              </button>
            </div>
          ))}
        </div>
      )}

      <div>
        <h4 className="text-sm font-semibold text-slate-900">{t("search_test.runs_title")}</h4>
        {runs.length === 0 ? (
          <p className="mt-2 text-sm text-slate-500">{t("search_test.runs_empty")}</p>
        ) : (
          <div className="mt-2 space-y-1">
            {runs.map((run) => (
              <SearchTestRunRow
                key={run.id}
                run={run}
                workspaceName={workspaceName}
                isOpen={openRunId === run.id}
                detail={openRunId === run.id ? runDetail : undefined}
                onToggle={() => setOpenRunId(openRunId === run.id ? null : run.id)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
