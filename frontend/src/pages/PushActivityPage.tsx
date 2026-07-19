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
import { useWorkspaces } from "@/hooks/useWorkspaces";
import type { GlobalJob, GlobalJobsFilters } from "@/lib/jobs.types";
import type { Job } from "@/lib/workspaces.types";
import { formatRelativeTime } from "@/lib/relativeTime";

const statusVariant: Record<Job["status"], "default" | "secondary" | "destructive"> = {
  done: "default",
  pending: "secondary",
  running: "secondary",
  error: "destructive",
};

const statusDotClass: Record<Job["status"], string> = {
  done: "bg-emerald-500",
  pending: "bg-slate-400",
  running: "bg-sky-500",
  error: "bg-rose-500",
};

const JOB_STATUSES: Job["status"][] = ["pending", "running", "done", "error"];

function StatusBadge({ status }: { status: Job["status"] }) {
  const { t } = useTranslation("push");
  return (
    <Badge variant={statusVariant[status]} className="gap-1.5 font-normal">
      <span className={`h-1.5 w-1.5 rounded-full ${statusDotClass[status]}`} />
      {t(`status.${status}`)}
    </Badge>
  );
}

function JobRow({ job }: { job: GlobalJob }) {
  const { t } = useTranslation("push");
  return (
    <TableRow>
      <TableCell className="font-medium text-slate-900">{job.workspace_name}</TableCell>
      <TableCell className="font-mono text-xs text-slate-600">{job.triggered_by}</TableCell>
      <TableCell>
        <StatusBadge status={job.status} />
      </TableCell>
      <TableCell className="text-xs text-slate-600">
        {t("files_summary", { changed: job.files_changed, skipped: job.files_skipped })}
      </TableCell>
      <TableCell className="text-xs text-slate-500">
        {job.started_at ? formatRelativeTime(job.started_at, t) : "—"}
      </TableCell>
    </TableRow>
  );
}

export function PushActivityPage() {
  const { t } = useTranslation("push");
  const [workspace, setWorkspace] = useState("");
  const [status, setStatus] = useState("");

  const filters: GlobalJobsFilters = {
    ...(workspace ? { workspace } : {}),
    ...(status ? { status: status as Job["status"] } : {}),
  };
  const { data: jobs, isLoading, isError } = useGlobalJobs(filters);
  const { data: workspaces = [] } = useWorkspaces();

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("description")}</p>
      </div>

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
                <TableHead>{t("table.trigger")}</TableHead>
                <TableHead>{t("table.status")}</TableHead>
                <TableHead>{t("table.files")}</TableHead>
                <TableHead>{t("table.date")}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {jobs.map((job) => (
                <JobRow key={job.id} job={job} />
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  );
}
