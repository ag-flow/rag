import { useTranslation } from "react-i18next";
import { useWorkspaceJobFiles } from "@/hooks/useWorkspaces";
import type { Job, JobFileEntry } from "@/lib/workspaces.types";

interface Props {
  name: string;
  job: Job;
}

const SIGN: Record<JobFileEntry["change_type"], string> = {
  added: "+",
  modified: "~",
  deleted: "−",
};

const COLOR: Record<JobFileEntry["change_type"], string> = {
  added: "text-green-700",
  modified: "text-amber-700",
  deleted: "text-red-700",
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString();
}

export function JobDetailPanel({ name, job }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading, isError } = useWorkspaceJobFiles(name, job.id, true);
  const files = data?.files ?? [];
  const hasError = job.status === "error" && job.error_message;

  return (
    <div className="border-t border-slate-100 px-3 py-2 bg-slate-50 text-xs">
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-slate-600 mb-2">
        <span>
          {t("jobs.detail.started")} : {fmt(job.started_at)}
        </span>
        <span>
          {t("jobs.detail.finished")} : {fmt(job.finished_at)}
        </span>
      </div>

      {hasError && (
        <div className="mb-2 rounded bg-red-50 px-2 py-1 text-red-700 font-mono">
          {job.error_message}
        </div>
      )}

      {isLoading && <p className="text-slate-500">{t("jobs.detail.loading")}</p>}
      {isError && <p className="text-red-600">{t("jobs.detail.error")}</p>}

      {!isLoading && !isError && files.length === 0 && !hasError && (
        <p className="text-slate-500">{t("jobs.detail.no_files")}</p>
      )}

      {files.length > 0 && (
        <>
          <p className="font-medium text-slate-700 mb-1">
            {t("jobs.detail.files", { count: data?.total ?? files.length })}
          </p>
          <ul className="space-y-0.5 font-mono">
            {files.map((f) => (
              <li key={`${f.change_type}:${f.path}`} className={COLOR[f.change_type]}>
                <span className="inline-block w-3">{SIGN[f.change_type]}</span> {f.path}
              </li>
            ))}
          </ul>
          {data && data.total > data.limit && (
            <p className="text-slate-400 mt-1">
              {t("jobs.detail.more", { count: data.total - data.limit })}
            </p>
          )}
        </>
      )}
    </div>
  );
}
