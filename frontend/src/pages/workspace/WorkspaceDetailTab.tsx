import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Info, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useRerankConfig } from "@/hooks/useRerank";
import { useLlmConfigs } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { workspacesApi } from "@/lib/workspaces";
import type { Workspace } from "@/lib/workspaces.types";
import { formatRelativeTime } from "@/lib/relativeTime";

/** Corps 409 renvoyé quand la recopie change le modèle d'embedding :
 * il faut confirmer la réindexation (re-vectorisation complète). */
function isIndexerChangeRequiresReindex(
  body: unknown,
): body is { error: string; current: string; requested: string } {
  return (
    typeof body === "object" &&
    body !== null &&
    "error" in body &&
    (body as { error: unknown }).error === "indexer_change_requires_reindex"
  );
}

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

/** « 3000 req/min · 500000 tokens/min » — null = règle désactivée. */
function formatLimits(
  rpm: number | null | undefined,
  tpm: number | null | undefined,
  t: ReturnType<typeof useTranslation>["t"],
): string | null {
  const parts = [
    rpm != null ? t("detail.limits.rpm", { value: rpm }) : null,
    tpm != null ? t("detail.limits.tpm", { value: tpm }) : null,
  ].filter(Boolean);
  return parts.length > 0 ? parts.join(" · ") : null;
}

export function WorkspaceDetailTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const qc = useQueryClient();
  const { data: rerankData, isLoading: rerankLoading } = useRerankConfig(workspace.name, enabled);
  const { data: llmConfigs = [] } = useLlmConfigs(workspace.name);

  // Recopie indexer/rerank/llm depuis l'endpoint d'ORIGINE du workspace.
  // 409 indexer_change_requires_reindex → dialog de confirmation puis retry
  // avec confirm=true (même protocole que le chunking, cf. ChunkingEngineSwitch).
  const [confirmReindex, setConfirmReindex] = useState<{
    current: string;
    requested: string;
  } | null>(null);
  const refreshMutation = useMutation({
    mutationFn: (confirm: boolean) => workspacesApi.refreshEndpoint(workspace.name, confirm),
    onSuccess: () => {
      setConfirmReindex(null);
      void qc.invalidateQueries({ queryKey: ["workspace", workspace.name] });
      void qc.invalidateQueries({ queryKey: ["workspace", workspace.name, "rerank"] });
      void qc.invalidateQueries({ queryKey: ["playground", workspace.name, "llm-configs"] });
      toast({ title: t("detail.refresh.done") });
    },
    onError: (err) => {
      if (
        err instanceof ApiError &&
        err.status === 409 &&
        isIndexerChangeRequiresReindex(err.body)
      ) {
        setConfirmReindex({ current: err.body.current, requested: err.body.requested });
        return;
      }
      setConfirmReindex(null);
      toast({ title: t("detail.refresh.error"), variant: "destructive" });
    },
  });

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
            {t("detail.ids.label")}: <span className="font-medium">{workspace.label}</span>
          </div>
          <div>
            {t("detail.ids.name")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.name}</code>
          </div>
          <div>
            {t("detail.ids.id")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.id}</code>
          </div>
          <div>
            {t("detail.ids.description")}:{" "}
            {workspace.description ? (
              <span>{workspace.description}</span>
            ) : (
              <span className="italic text-slate-400">{t("detail.ids.description_empty")}</span>
            )}
          </div>
        </div>
      </section>

      {/* Rafraîchir depuis l'endpoint d'ORIGINE (recopie indexer/rerank/llm). */}
      <section className="flex items-center justify-between rounded-md border bg-slate-50 px-4 py-3">
        <p className="text-sm text-slate-600">{t("detail.refresh.help")}</p>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!workspace.endpoint_id || refreshMutation.isPending}
          title={!workspace.endpoint_id ? t("detail.refresh.no_link") : undefined}
          onClick={() => refreshMutation.mutate(false)}
        >
          <RefreshCw className="h-3.5 w-3.5" />
          <span className="ml-1">{t("detail.refresh.button")}</span>
        </Button>
      </section>

      {/* Section LLM : exécution des prompts (copié de l'endpoint à la création) */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.llm.title")}
        </h3>
        {llmConfigs.length === 0 ? (
          <p className="text-sm text-slate-500">{t("detail.llm.empty")}</p>
        ) : (
          <dl className="grid grid-cols-2 gap-2 text-sm">
            {llmConfigs.map((c) => (
              <div key={c.id} className="contents">
                <dt className="text-slate-500">
                  {c.provider}
                  {!c.enabled && (
                    <span className="ml-1 text-xs text-slate-400">({t("detail.llm.disabled")})</span>
                  )}
                </dt>
                <dd className="font-mono">
                  {c.model}
                  {c.base_url ? <span className="text-slate-400"> · {c.base_url}</span> : null}
                  {formatLimits(c.rpm_limit, c.tpm_limit, t) && (
                    <span className="block text-xs text-slate-400">
                      {t("detail.limits.title")} : {formatLimits(c.rpm_limit, c.tpm_limit, t)}
                    </span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
        )}
      </section>

      {/* Section 3 : Reranking */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("rerank.title")}
        </h3>
        {rerankLoading ? (
          <div className="flex h-12 items-center">
            <LoadingSpinner />
          </div>
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
            {formatLimits(rerankData.rpm_limit, rerankData.tpm_limit, t) && (
              <>
                <dt className="text-slate-500">{t("detail.limits.title")}</dt>
                <dd className="font-mono">
                  {formatLimits(rerankData.rpm_limit, rerankData.tpm_limit, t)}
                </dd>
              </>
            )}
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
          {formatLimits(workspace.indexer.rpm_limit, workspace.indexer.tpm_limit, t) && (
            <>
              <dt className="text-slate-500">{t("detail.limits.title")}</dt>
              <dd className="font-mono">
                {formatLimits(workspace.indexer.rpm_limit, workspace.indexer.tpm_limit, t)}
              </dd>
            </>
          )}
        </dl>
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
          <Info className="h-4 w-4 text-amber-600 mt-0.5 shrink-0" />
          <p className="text-amber-900">{t("model.immutableNote")}</p>
        </div>
      </section>

      {/* Confirmation : la recopie change le modèle d'embedding → réindexation */}
      <AlertDialog
        open={confirmReindex !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmReindex(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("detail.refresh.confirm.title")}</AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm">
                <p>{t("detail.refresh.confirm.intro")}</p>
                <p>
                  <span className="font-medium">{t("detail.refresh.confirm.current")}</span>
                  <br />
                  <span className="font-mono text-slate-700">{confirmReindex?.current}</span>
                </p>
                <p>
                  <span className="font-medium">{t("detail.refresh.confirm.requested")}</span>
                  <br />
                  <span className="font-mono text-slate-700">{confirmReindex?.requested}</span>
                </p>
                <p className="text-slate-500">{t("detail.refresh.confirm.consequence")}</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={refreshMutation.isPending}>
              {t("detail.refresh.confirm.cancel")}
            </AlertDialogCancel>
            <AlertDialogAction
              onClick={() => refreshMutation.mutate(true)}
              disabled={refreshMutation.isPending}
              className="bg-amber-600 hover:bg-amber-700"
            >
              {t("detail.refresh.confirm.confirm")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
