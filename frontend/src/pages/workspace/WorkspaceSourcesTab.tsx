import { useState, useEffect, useRef } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Plus, MoreHorizontal, ChevronRight, ChevronDown, Play } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
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
import { useWorkspaceSources, useTriggerSourceSync } from "@/hooks/useWorkspaces";
import { useDisableWebhook } from "@/hooks/useSourceWebhooks";
import { useJobLogs } from "@/hooks/useJobLogs";
import type { Source } from "@/lib/workspaces.types";
import { formatRelativeTime } from "@/lib/relativeTime";
import { AddSourceDialog } from "./AddSourceDialog";
import { DeleteSourceAlert } from "./DeleteSourceAlert";
import { EnableWebhookDialog } from "./EnableWebhookDialog";
import { RotateWebhookSecretDialog } from "./RotateWebhookSecretDialog";

interface Props {
  name: string;
  enabled: boolean;
}

export function WorkspaceSourcesTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { t: tWh } = useTranslation("git_webhooks");
  const { data, isLoading } = useWorkspaceSources(name, enabled);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [editSource, setEditSource] = useState<Source | null>(null);
  const [deleteId, setDeleteId] = useState<string | null>(null);
  const disableMutation = useDisableWebhook(name);
  const [webhookEnableTarget, setWebhookEnableTarget] = useState<string | null>(null);
  const [webhookRotateTarget, setWebhookRotateTarget] = useState<string | null>(null);
  const [webhookDisableTarget, setWebhookDisableTarget] = useState<string | null>(null);

  if (isLoading) return <LoadingSpinner />;
  const sources = data ?? [];

  const toggle = (id: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  return (
    <>
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-sm font-semibold text-slate-900">
          {t("sources.title", { count: sources.length })}
        </h3>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="h-3.5 w-3.5" /> {t("sources.addButton")}
        </Button>
      </div>

      {sources.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("sources.empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {sources.map((source: Source) => {
            const isOpen = expanded.has(source.id);
            return (
              <div key={source.id} className="rounded border border-slate-200 bg-white">
                <button
                  type="button"
                  onClick={() => toggle(source.id)}
                  className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50"
                >
                  <div className="flex items-center gap-2 text-sm min-w-0">
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5 shrink-0" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                    )}
                    {source.name && (
                      <span className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-xs font-semibold text-slate-700 shrink-0">
                        {source.name}
                      </span>
                    )}
                    <code className="font-mono text-xs truncate">{source.config.url}</code>
                    <span className="text-slate-500 shrink-0">· {source.config.branch}</span>
                    <span className="text-slate-400 shrink-0">
                      ·{" "}
                      {source.last_indexed_at
                        ? formatRelativeTime(source.last_indexed_at, t)
                        : t("sources.neverSynced")}
                    </span>
                    {source.webhook_enabled ? (
                      <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-emerald-100 text-emerald-700 shrink-0">
                        {tWh("badge_webhook")}
                      </span>
                    ) : (
                      <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-slate-100 text-slate-500 shrink-0">
                        {tWh("badge_schedule")}
                      </span>
                    )}
                  </div>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        size="sm"
                        variant="ghost"
                        className="px-2"
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="h-3.5 w-3.5" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem onSelect={() => setEditSource(source)}>
                        {t("sources.editAction")}
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      {!source.webhook_enabled ? (
                        <DropdownMenuItem
                          onSelect={() => setWebhookEnableTarget(source.name ?? source.id)}
                        >
                          {tWh("menu_enable")}
                        </DropdownMenuItem>
                      ) : (
                        <>
                          <DropdownMenuItem
                            onSelect={() => setWebhookRotateTarget(source.name ?? source.id)}
                          >
                            {tWh("menu_rotate")}
                          </DropdownMenuItem>
                          <DropdownMenuItem
                            onSelect={() => setWebhookDisableTarget(source.name ?? source.id)}
                            className="text-rose-600"
                          >
                            {tWh("menu_disable")}
                          </DropdownMenuItem>
                        </>
                      )}
                      <DropdownMenuSeparator />
                      <DropdownMenuItem
                        onSelect={() => setDeleteId(source.id)}
                        className="text-red-600"
                      >
                        {t("sources.deleteAction")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </button>
                {isOpen && (
                  <div className="border-t border-slate-100 px-3 py-2 text-xs text-slate-600 space-y-1 bg-slate-50">
                    <div className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
                      {source.name && (
                        <>
                          <span className="text-slate-400">{t("sources.fields.source_name")}</span>
                          <code className="font-mono">{source.name}</code>
                        </>
                      )}
                      <span className="text-slate-400">{t("sources.fields.url")}</span>
                      <code className="font-mono break-all">{source.config.url}</code>
                      <span className="text-slate-400">{t("sources.fields.branch")}</span>
                      <code className="font-mono">{source.config.branch}</code>
                      <span className="text-slate-400">{t("sources.fields.auth_value")}</span>
                      <span>
                        {source.config.auth_ref
                          ? t("sources.fields.auth_status_set")
                          : t("sources.fields.auth_status_none")}
                      </span>
                      <span className="text-slate-400">{t("sources.fields.include")}</span>
                      <code className="font-mono">{source.config.include.join(", ") || "—"}</code>
                      <span className="text-slate-400">{t("sources.fields.exclude")}</span>
                      <code className="font-mono">{source.config.exclude.join(", ") || "—"}</code>
                    </div>
                    <SourceSyncPanel workspaceName={name} sourceId={source.id} />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <AddSourceDialog name={name} open={addOpen} onOpenChange={setAddOpen} />
      <AddSourceDialog
        name={name}
        open={editSource !== null}
        onOpenChange={(o) => !o && setEditSource(null)}
        {...(editSource !== null ? { source: editSource } : {})}
      />
      <DeleteSourceAlert name={name} sourceId={deleteId} onClose={() => setDeleteId(null)} />

      {webhookEnableTarget && (
        <EnableWebhookDialog
          workspaceName={name}
          sourceName={webhookEnableTarget}
          open={!!webhookEnableTarget}
          onOpenChange={(o) => {
            if (!o) setWebhookEnableTarget(null);
          }}
        />
      )}
      {webhookRotateTarget && (
        <RotateWebhookSecretDialog
          workspaceName={name}
          sourceName={webhookRotateTarget}
          open={!!webhookRotateTarget}
          onOpenChange={(o) => {
            if (!o) setWebhookRotateTarget(null);
          }}
        />
      )}
      <AlertDialog
        open={!!webhookDisableTarget}
        onOpenChange={(o) => {
          if (!o) setWebhookDisableTarget(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{tWh("disable_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{tWh("disable_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{tWh("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={() => {
                if (webhookDisableTarget) {
                  disableMutation.mutate(webhookDisableTarget, {
                    onSuccess: () => setWebhookDisableTarget(null),
                  });
                }
              }}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {tWh("disable_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </>
  );
}

// ─── Source sync panel ────────────────────────────────────────────────────────

interface SyncPanelProps {
  workspaceName: string;
  sourceId: string;
}

function SourceSyncPanel({ workspaceName, sourceId }: SyncPanelProps) {
  const { t } = useTranslation("workspace");
  const qc = useQueryClient();
  const jobQueryKey = ["source-active-job", workspaceName, sourceId] as const;

  // jobId stocké dans le cache Query : survit aux navigations et aux toggle d'accordion
  const { data: jobId = null } = useQuery<string | null>({
    queryKey: jobQueryKey,
    queryFn: () => null,
    enabled: false,
    staleTime: Infinity,
    gcTime: Infinity,
  });

  const trigger = useTriggerSourceSync(workspaceName);
  const { lines, jobStatus } = useJobLogs(jobId);
  const logEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [lines]);

  const handleRun = () => {
    trigger.mutate(sourceId, {
      onSuccess: (job) => qc.setQueryData<string | null>(jobQueryKey, job.id),
    });
  };

  const isRunning = trigger.isPending || jobStatus === "running";

  return (
    <div className="pt-2 border-t border-slate-200 mt-1">
      <Button
        size="sm"
        variant="outline"
        onClick={handleRun}
        disabled={isRunning}
        className="h-7 text-xs"
      >
        <Play className="h-3 w-3 mr-1" />
        {isRunning ? t("sources.sync.running") : t("sources.sync.run")}
      </Button>

      {jobId !== null && (
        <div className="mt-2 rounded bg-slate-900 font-mono text-xs p-2 max-h-40 overflow-y-auto">
          {lines.map((l, i) => (
            <div
              key={i}
              className={
                l.level === "error"
                  ? "text-red-400"
                  : l.level === "warning"
                    ? "text-yellow-300"
                    : "text-slate-300"
              }
            >
              {l.msg}
            </div>
          ))}
          {jobStatus === "done" && (
            <div className="text-green-400 mt-1">✓ {t("sources.sync.done")}</div>
          )}
          {jobStatus === "error" && (
            <div className="text-red-400 mt-1">✗ {t("sources.sync.error")}</div>
          )}
          <div ref={logEndRef} />
        </div>
      )}
    </div>
  );
}
