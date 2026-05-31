import { useTranslation } from "react-i18next";
import { AlertTriangle, Info } from "lucide-react";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useRerankConfig } from "@/hooks/useRerank";
import type { Workspace } from "@/lib/workspaces.types";
import { formatRelativeTime } from "@/lib/relativeTime";

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceDetailTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data: rerankData, isLoading: rerankLoading } = useRerankConfig(workspace.name, enabled);

  return (
    <div className="space-y-6">
      {/* Section 1 : Stats */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.stats.title")}
        </h3>
        <div className="text-sm text-slate-700">
          {t("detail.stats.sources", { count: workspace.sources_count })}
          {" · "}
          {t("detail.stats.documents", { count: workspace.documents_count })}
          {" · "}
          {t("detail.stats.lastIndexed", {
            when: workspace.last_indexed_at
              ? formatRelativeTime(workspace.last_indexed_at, t)
              : "—",
          })}
        </div>
      </section>

      {/* Section 2 : Identifiants read-only */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.ids.title")}
        </h3>
        <div className="text-sm text-slate-700 space-y-1">
          <div>
            {t("detail.ids.name")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.name}</code>
          </div>
          <div>
            {t("detail.ids.id")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.id}</code>
          </div>
        </div>
      </section>

      {/* Section 3 : Reranking */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("rerank.title")}
        </h3>
        {rerankLoading ? (
          <div className="flex h-12 items-center"><LoadingSpinner /></div>
        ) : !rerankData ? (
          <p className="text-sm text-slate-500">{t("rerank.description.empty")}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-2 text-sm mb-3">
            <dt className="text-slate-500">{t("rerank.fields.provider")}</dt>
            <dd className="font-mono">{rerankData.provider}</dd>
            <dt className="text-slate-500">{t("rerank.fields.model")}</dt>
            <dd className="font-mono">{rerankData.model}</dd>
            <dt className="text-slate-500">{t("rerank.fields.baseUrl")}</dt>
            <dd className="font-mono">{rerankData.base_url ?? "—"}</dd>
            <dt className="text-slate-500">{t("rerank.fields.apiKeyRef")}</dt>
            <dd className="font-mono">{rerankData.api_key_ref ?? "—"}</dd>
            <dt className="text-slate-500">{t("rerank.fields.topK")}</dt>
            <dd className="font-mono">{rerankData.top_k_pre_rerank}</dd>
          </dl>
        )}
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <p className="text-amber-900">{t("rerank.warning")}</p>
        </div>
      </section>

      {/* Section 4 : Modèle d'indexation (immuable) */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("model.title")}
        </h3>
        <dl className="grid grid-cols-2 gap-2 text-sm mb-3">
          <dt className="text-slate-500">{t("model.provider")}</dt>
          <dd className="font-mono">{workspace.indexer.provider}</dd>
          <dt className="text-slate-500">{t("model.model")}</dt>
          <dd className="font-mono">{workspace.indexer.model}</dd>
          <dt className="text-slate-500">{t("model.base_url")}</dt>
          <dd className="font-mono">{workspace.indexer.base_url ?? "—"}</dd>
          <dt className="text-slate-500">{t("model.api_key_ref")}</dt>
          <dd className="font-mono">{workspace.indexer.api_key_ref ?? "—"}</dd>
        </dl>
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
          <Info className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <p className="text-amber-900">{t("model.immutableNote")}</p>
        </div>
      </section>
    </div>
  );
}
