import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useRerankConfig } from "@/hooks/useRerank";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceRerankTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useRerankConfig(workspace.name, enabled);

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-slate-900">{t("rerank.title")}</h3>

      {!data ? (
        <p className="text-sm text-slate-500">{t("rerank.description.empty")}</p>
      ) : (
        <dl className="grid grid-cols-2 gap-2 text-sm">
          <dt className="text-slate-500">{t("rerank.fields.provider")}</dt>
          <dd className="font-mono">{data.provider}</dd>
          <dt className="text-slate-500">{t("rerank.fields.model")}</dt>
          <dd className="font-mono">{data.model}</dd>
          <dt className="text-slate-500">{t("rerank.fields.baseUrl")}</dt>
          <dd className="font-mono">{data.base_url ?? "—"}</dd>
          <dt className="text-slate-500">{t("rerank.fields.apiKeyRef")}</dt>
          <dd className="font-mono">{data.api_key_ref ?? "—"}</dd>
          <dt className="text-slate-500">{t("rerank.fields.topK")}</dt>
          <dd className="font-mono">{data.top_k_pre_rerank}</dd>
        </dl>
      )}

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("rerank.warning")}</p>
      </div>
    </div>
  );
}
