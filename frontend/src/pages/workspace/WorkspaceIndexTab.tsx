// frontend/src/pages/workspace/WorkspaceIndexTab.tsx
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { Switch } from "@/components/ui/switch";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { useIndexKeyDetail, useIndexKeys, usePatchStrategy } from "@/hooks/useIndexKeys";
import type { PathStrategyEntry } from "@/lib/workspaces.types";

interface Props {
  workspaceName: string;
  enabled: boolean;
}

export function WorkspaceIndexTab({ workspaceName, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useIndexKeys(workspaceName, enabled);
  const [filter, setFilter] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  if (isLoading) return <LoadingSpinner />;

  const paths = (data?.paths ?? []).filter((e) =>
    e.path.toLowerCase().includes(filter.toLowerCase()),
  );

  const toggle = (path: string) =>
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(path)) next.delete(path);
      else next.add(path);
      return next;
    });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {t("index.title", { count: data?.total ?? 0 })}
        </h3>
        <input
          type="text"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder={t("index.search_placeholder")}
          className="h-7 rounded border border-slate-300 px-2 text-xs focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>

      {paths.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("index.empty")}
        </div>
      ) : (
        <div className="space-y-1">
          {paths.map((entry) => (
            <PathRow
              key={entry.path}
              entry={entry}
              workspaceName={workspaceName}
              isOpen={expanded.has(entry.path)}
              onToggle={() => toggle(entry.path)}
            />
          ))}
        </div>
      )}
    </div>
  );
}

interface PathRowProps {
  entry: PathStrategyEntry;
  workspaceName: string;
  isOpen: boolean;
  onToggle: () => void;
}

function PathRow({ entry, workspaceName, isOpen, onToggle }: PathRowProps) {
  const { t } = useTranslation("workspace");
  const patch = usePatchStrategy(workspaceName);
  const { data: detail, isLoading: detailLoading } = useIndexKeyDetail(
    workspaceName,
    entry.path,
    isOpen,
  );

  const isFromFile = entry.updated_by === "strategy_file";
  const isAppend = entry.strategy === "append";

  const handleStrategyToggle = (checked: boolean) => {
    patch.mutate({ path: entry.path, strategy: checked ? "append" : "replace" });
  };

  return (
    <div className="rounded border border-slate-200 bg-white">
      <button
        type="button"
        onClick={onToggle}
        className="w-full flex items-center justify-between px-3 py-2 text-left hover:bg-slate-50"
      >
        <div className="flex items-center gap-2 text-sm min-w-0">
          {isOpen ? (
            <ChevronDown className="h-3.5 w-3.5 shrink-0" />
          ) : (
            <ChevronRight className="h-3.5 w-3.5 shrink-0" />
          )}
          <code className="font-mono text-xs truncate">{entry.path}</code>
          <span
            className={`rounded px-1.5 py-0.5 text-xs font-medium shrink-0 ${
              isAppend
                ? "bg-blue-100 text-blue-700"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            {isAppend ? t("index.strategy_append") : t("index.strategy_replace")}
          </span>
          {isFromFile && (
            <span className="rounded px-1.5 py-0.5 text-xs font-medium bg-amber-100 text-amber-700 shrink-0">
              {t("index.badge_file")}
            </span>
          )}
          <span className="text-slate-400 text-xs shrink-0">
            {t("index.stats", {
              chunks: entry.chunk_count,
              versions: entry.version_count,
            })}
          </span>
        </div>

        <div
          className="flex items-center gap-2 shrink-0"
          onClick={(e) => e.stopPropagation()}
        >
          {isFromFile ? (
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span>
                    <Switch checked={isAppend} disabled />
                  </span>
                </TooltipTrigger>
                <TooltipContent>
                  <p className="max-w-xs text-xs">{t("index.toggle_tooltip_file")}</p>
                </TooltipContent>
              </Tooltip>
            </TooltipProvider>
          ) : (
            <Switch
              checked={isAppend}
              onCheckedChange={handleStrategyToggle}
              disabled={patch.isPending}
            />
          )}
        </div>
      </button>

      {isOpen && (
        <div className="border-t border-slate-100 bg-slate-50 px-3 py-2 space-y-3">
          {detailLoading ? (
            <LoadingSpinner />
          ) : (
            (detail?.versions ?? []).map((vg) => (
              <div key={vg.indexed_at} className="space-y-1">
                <p className="text-xs font-semibold text-slate-600">
                  {t("index.version_label", {
                    date: new Date(vg.indexed_at).toLocaleString(),
                  })}
                </p>
                {vg.chunks.map((chunk) => (
                  <div
                    key={chunk.chunk_index}
                    className="rounded border border-slate-200 bg-white p-2 text-xs"
                  >
                    <p className="font-medium text-slate-500 mb-1">
                      {t("index.chunk_label", { index: chunk.chunk_index })}
                    </p>
                    <p className="text-slate-700 whitespace-pre-wrap line-clamp-4">
                      {chunk.content}
                    </p>
                    {Object.keys(chunk.metadata).length > 0 && (
                      <details className="mt-1">
                        <summary className="cursor-pointer text-slate-400">
                          {t("index.metadata_label")}
                        </summary>
                        <pre className="mt-1 text-xs text-slate-500 overflow-auto">
                          {JSON.stringify(chunk.metadata, null, 2)}
                        </pre>
                      </details>
                    )}
                  </div>
                ))}
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
