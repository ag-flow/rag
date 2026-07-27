import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useGlobalJobs } from "@/hooks/useGlobalJobs";
import { useWorkspaces, useWorkspaceJob } from "@/hooks/useWorkspaces";
import type { GlobalJob, GlobalJobsFilters } from "@/lib/jobs.types";
import type { Job, JobSource } from "@/lib/workspaces.types";
import { formatDurationMs } from "@/lib/duration";
import { formatRelativeTime } from "@/lib/relativeTime";
import { JobDetailPanel } from "@/pages/workspace/JobDetailPanel";
import { LoadGatePanel } from "@/pages/push/LoadGatePanel";

const JOB_SOURCES: JobSource[] = ["rest_api", "webhook", "git", "admin"];

const sourceClass: Record<JobSource, string> = {
  rest_api: "bg-violet-50 text-violet-700",
  webhook: "bg-amber-50 text-amber-700",
  git: "bg-sky-50 text-sky-700",
  admin: "bg-slate-100 text-slate-600",
};

function SourceBadge({ source }: { source: JobSource }) {
  const { t } = useTranslation("push");
  return (
    <span className={`rounded px-1.5 py-0.5 text-xs font-medium ${sourceClass[source]}`}>
      {t(`source.${source}`)}
    </span>
  );
}

const statusVariant: Record<Job["status"], "default" | "secondary" | "destructive"> = {
  done: "default",
  pending: "secondary",
  running: "secondary",
  error: "destructive",
  rejected: "destructive",
};

const statusDotClass: Record<Job["status"], string> = {
  done: "bg-emerald-500",
  pending: "bg-slate-400",
  running: "bg-sky-500",
  error: "bg-rose-500",
  rejected: "bg-rose-600",
};

const JOB_STATUSES: Job["status"][] = ["pending", "running", "done", "error", "rejected"];

function StatusBadge({ status }: { status: Job["status"] }) {
  const { t } = useTranslation("push");
  return (
    <Badge variant={statusVariant[status]} className="gap-1.5 font-normal">
      <span className={`h-1.5 w-1.5 rounded-full ${statusDotClass[status]}`} />
      {t(`status.${status}`)}
    </Badge>
  );
}

function JobRow({
  job,
  isOpen,
  onToggle,
}: {
  job: GlobalJob;
  isOpen: boolean;
  onToggle: () => void;
}) {
  const { t } = useTranslation("push");
  // Un rejet d'ingestion n'a pas de job → ni re-fetch ni drill-down (le motif
  // est déjà dans error_message).
  const isRejected = job.status === "rejected";
  const { data: fresh } = useWorkspaceJob(job.workspace_name, job.id, isOpen && !isRejected);
  const current: Job = fresh ?? job;

  return (
    <>
      <TableRow
        onClick={isRejected ? undefined : onToggle}
        aria-expanded={isRejected ? undefined : isOpen}
        aria-label={isRejected ? undefined : t("table.detail_aria")}
        className={isRejected ? "" : `cursor-pointer ${isOpen ? "bg-slate-50" : ""}`}
      >
        <TableCell className="font-medium text-slate-900">{job.workspace_name ?? "—"}</TableCell>
        <TableCell>
          <SourceBadge source={current.source} />
        </TableCell>
        <TableCell className="font-mono text-xs text-slate-600">{current.triggered_by}</TableCell>
        <TableCell className="max-w-[220px] truncate font-mono text-xs text-slate-700">
          {current.path ?? "—"}
        </TableCell>
        <TableCell>
          <StatusBadge status={current.status} />
        </TableCell>
        <TableCell className="text-xs text-slate-600">
          {isRejected ? (
            <span className="text-rose-700">{current.error_message}</span>
          ) : (
            t("files_summary", {
              changed: current.files_changed,
              skipped: current.files_skipped,
            })
          )}
        </TableCell>
        <TableCell className="text-right font-mono text-xs text-slate-600">
          {formatDurationMs(current.duration_ms)}
        </TableCell>
        <TableCell className="text-xs text-slate-500">
          {current.started_at ? formatRelativeTime(current.started_at, t) : "—"}
        </TableCell>
      </TableRow>
      {isOpen && !isRejected && job.workspace_name && (
        <TableRow>
          <TableCell colSpan={8} className="p-0">
            <JobDetailPanel name={job.workspace_name} job={current} />
          </TableCell>
        </TableRow>
      )}
    </>
  );
}

export function PushActivityPage() {
  const { t } = useTranslation("push");
  const [workspace, setWorkspace] = useState("");
  const [status, setStatus] = useState("");
  const [source, setSource] = useState("");
  const [openJobId, setOpenJobId] = useState<string | null>(null);

  const filters: GlobalJobsFilters = {
    ...(workspace ? { workspace } : {}),
    ...(status ? { status: status as Job["status"] } : {}),
    ...(source ? { source: source as JobSource } : {}),
  };
  const { data: jobs, isLoading, isError } = useGlobalJobs(filters);
  const { data: workspaces = [] } = useWorkspaces();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("description")}</p>
      </div>

      <LoadGatePanel />

      <div className="flex gap-2">
        <select
          className="border rounded px-2 py-1 text-sm"
          aria-label={t("filters.workspace_label")}
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
        >
          <option value="">{t("filters.all_workspaces")}</option>
          {workspaces.map((ws) => (
            <option key={ws.id} value={ws.name}>
              {ws.name}
            </option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          aria-label={t("filters.status_label")}
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">{t("filters.all_statuses")}</option>
          {JOB_STATUSES.map((s) => (
            <option key={s} value={s}>
              {t(`status.${s}`)}
            </option>
          ))}
        </select>
        <select
          className="border rounded px-2 py-1 text-sm"
          aria-label={t("filters.source_label")}
          value={source}
          onChange={(e) => setSource(e.target.value)}
        >
          <option value="">{t("filters.all_sources")}</option>
          {JOB_SOURCES.map((s) => (
            <option key={s} value={s}>
              {t(`source.${s}`)}
            </option>
          ))}
        </select>
      </div>

      {isLoading && <LoadingSpinner />}
      {isError && <p className="text-sm text-rose-600">{t("error")}</p>}

      {jobs && jobs.length === 0 && (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      )}

      {jobs && jobs.length > 0 && (
        <div className="rounded-md border border-slate-200 bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("table.workspace")}</TableHead>
                <TableHead>{t("table.source")}</TableHead>
                <TableHead>{t("table.trigger")}</TableHead>
                <TableHead>{t("table.path")}</TableHead>
                <TableHead>{t("table.status")}</TableHead>
                <TableHead>{t("table.files")}</TableHead>
                <TableHead className="text-right">{t("table.duration")}</TableHead>
                <TableHead>{t("table.date")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  isOpen={openJobId === job.id}
                  onToggle={() => setOpenJobId((cur) => (cur === job.id ? null : job.id))}
                />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
