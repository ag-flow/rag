import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { ChevronDown, ChevronRight } from "lucide-react";
import { useWorkspaceJobs } from "@/hooks/useWorkspaces";
import type { Job } from "@/lib/workspaces.types";

interface Props { name: string; enabled: boolean; }

const statusVariant: Record<Job["status"], "default" | "secondary" | "destructive"> = {
  done: "default",
  pending: "secondary",
  running: "secondary",
  error: "destructive",
};

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return "à l'instant";
  if (m < 60) return `il y a ${m} min`;
  const h = Math.floor(m / 60);
  if (h < 24) return `il y a ${h} h`;
  return `il y a ${Math.floor(h / 24)} j`;
}

function formatDuration(ms: number | null): string {
  if (ms === null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

export function WorkspaceJobsTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaceJobs(name, enabled);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (isLoading) return <LoadingSpinner />;
  const jobs = data ?? [];

  if (jobs.length === 0) {
    return <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">{t("jobs.empty")}</div>;
  }

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id); else next.add(id);
      return next;
    });
  };

  return (
    <div>
      <h3 className="text-sm font-semibold text-slate-900 mb-3">{t("jobs.title", { count: jobs.length })}</h3>
      <div className="rounded-md border border-slate-200 bg-white">
        {jobs.map((job: Job) => {
          const hasError = job.status === "error" && job.error_message;
          const isOpen = expanded.has(job.id);
          return (
            <div key={job.id} className="border-b border-slate-100 last:border-b-0">
              <button
                type="button"
                onClick={() => hasError && toggle(job.id)}
                disabled={!hasError}
                className="w-full flex items-center gap-3 px-3 py-2 text-left hover:bg-slate-50 disabled:cursor-default"
              >
                {hasError ? (isOpen ? <ChevronDown className="h-3.5 w-3.5" /> : <ChevronRight className="h-3.5 w-3.5" />) : <span className="w-3.5" />}
                <Badge variant={statusVariant[job.status]} className="font-mono text-xs">{job.status}</Badge>
                <span className="text-xs text-slate-600 font-mono">{job.triggered_by}</span>
                <span className="text-xs text-slate-700">
                  {t("jobs.changes", { changed: job.files_changed, skipped: job.files_skipped })}
                </span>
                <span className="text-xs text-slate-500 ml-auto">{formatDuration(job.duration_ms)}</span>
                <span className="text-xs text-slate-500">{relativeTime(job.started_at)}</span>
              </button>
              {isOpen && hasError && (
                <div className="border-t border-slate-100 px-3 py-2 bg-red-50 text-xs text-red-700 font-mono">
                  {job.error_message}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
