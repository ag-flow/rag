import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, MoreHorizontal, ChevronRight, ChevronDown } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useWorkspaceSources } from "@/hooks/useWorkspaces";
import type { Source } from "@/lib/workspaces.types";
import { AddSourceDialog } from "./AddSourceDialog";
import { DeleteSourceAlert } from "./DeleteSourceAlert";

interface Props {
  name: string;
  enabled: boolean;
}

function relativeTimeRaw(iso: string | null): { key: string; count: number } | null {
  if (!iso) return null;
  const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
  if (m < 1) return { key: "time.justNow", count: 0 };
  if (m < 60) return { key: "time.minutesAgo", count: m };
  const h = Math.floor(m / 60);
  if (h < 24) return { key: "time.hoursAgo", count: h };
  return { key: "time.daysAgo", count: Math.floor(h / 24) };
}

export function WorkspaceSourcesTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaceSources(name, enabled);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [addOpen, setAddOpen] = useState(false);
  const [deleteId, setDeleteId] = useState<string | null>(null);

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
                  <div className="flex items-center gap-2 text-sm">
                    {isOpen ? (
                      <ChevronDown className="h-3.5 w-3.5" />
                    ) : (
                      <ChevronRight className="h-3.5 w-3.5" />
                    )}
                    <code className="font-mono text-xs">{source.config.url}</code>
                    <span className="text-slate-500">· {source.config.branch}</span>
                    <span className="text-slate-400">
                      ·{" "}
                      {(() => {
                        const rel = relativeTimeRaw(source.last_indexed_at);
                        if (!rel) return t("sources.neverSynced");
                        return rel.key === "time.justNow"
                          ? t("time.justNow")
                          : t(rel.key, { count: rel.count });
                      })()}
                    </span>
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
                    <div>
                      {t("sources.fields.auth_ref")}: <code>{source.config.auth_ref ?? "—"}</code>
                    </div>
                    <div>
                      {t("sources.fields.include")}:{" "}
                      <code>{source.config.include.join(", ") || "—"}</code>
                    </div>
                    <div>
                      {t("sources.fields.exclude")}:{" "}
                      <code>{source.config.exclude.join(", ") || "—"}</code>
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      <AddSourceDialog name={name} open={addOpen} onOpenChange={setAddOpen} />
      <DeleteSourceAlert name={name} sourceId={deleteId} onClose={() => setDeleteId(null)} />
    </>
  );
}
