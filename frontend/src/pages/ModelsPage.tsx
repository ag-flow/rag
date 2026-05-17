import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, MoreHorizontal, ChevronDown, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { useModels } from "@/hooks/useModels";
import type { ModelEntry } from "@/lib/models.types";
import { AddModelDialog } from "@/pages/models/AddModelDialog";
import { DeleteModelAlert } from "@/pages/models/DeleteModelAlert";

function useRelativeTime() {
  const { t } = useTranslation("models");
  return (iso: string): string => {
    const m = Math.floor((Date.now() - new Date(iso).getTime()) / 60_000);
    if (m < 1) return t("time.now");
    if (m < 60) return t("time.minutes", { count: m });
    const h = Math.floor(m / 60);
    if (h < 24) return t("time.hours", { count: h });
    return t("time.days", { count: Math.floor(h / 24) });
  };
}

export function ModelsPage() {
  const { t } = useTranslation("models");
  const formatRel = useRelativeTime();
  const { data, isLoading } = useModels();
  const [addOpen, setAddOpen] = useState(false);
  const [toDelete, setToDelete] = useState<{ provider: string; model: string } | null>(null);
  const [expanded, setExpanded] = useState<Set<string>>(new Set());

  const grouped = useMemo(() => {
    const map = new Map<string, ModelEntry[]>();
    for (const entry of data ?? []) {
      const list = map.get(entry.provider) ?? [];
      list.push(entry);
      map.set(entry.provider, list);
    }
    // Sort models alphabetically within each provider, providers sorted alphabetically.
    for (const list of map.values()) {
      list.sort((a, b) => a.model.localeCompare(b.model));
    }
    return Array.from(map.entries()).sort(([a], [b]) => a.localeCompare(b));
  }, [data]);

  // Open all sections by default once data loads.
  useEffect(() => {
    if (grouped.length > 0) {
      setExpanded((prev) => {
        // Only initialize once (when expanded is empty)
        if (prev.size > 0) return prev;
        return new Set(grouped.map(([p]) => p));
      });
    }
  }, [grouped]);

  const toggle = (provider: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      if (next.has(provider)) next.delete(provider);
      else next.add(provider);
      return next;
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  const models = data ?? [];

  return (
    <div className="p-6 max-w-3xl mx-auto">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
          <p className="text-sm text-slate-500 mt-1">{t("count", { count: models.length })}</p>
        </div>
        <Button onClick={() => setAddOpen(true)}>
          <Plus className="h-4 w-4" /> {t("add")}
        </Button>
      </div>

      {models.length === 0 ? (
        <div className="rounded-md border border-dashed border-slate-300 p-12 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="rounded-md border bg-white divide-y divide-slate-200">
          {grouped.map(([provider, entries]) => {
            const isOpen = expanded.has(provider);
            return (
              <div key={provider}>
                <button
                  type="button"
                  onClick={() => toggle(provider)}
                  className="w-full flex items-center justify-between px-4 py-3 text-left hover:bg-slate-50"
                >
                  <span className="font-medium text-slate-900 flex items-center gap-2">
                    {isOpen ? (
                      <ChevronDown className="h-4 w-4 text-slate-500" />
                    ) : (
                      <ChevronRight className="h-4 w-4 text-slate-500" />
                    )}
                    {provider}{" "}
                    <span className="text-slate-500 font-normal">
                      {t("section.count", { count: entries.length })}
                    </span>
                  </span>
                </button>
                {isOpen && (
                  <ul className="divide-y divide-slate-100 border-t border-slate-100">
                    {entries.map((entry) => (
                      <li
                        key={`${entry.provider}/${entry.model}`}
                        className="flex items-center justify-between px-4 py-2"
                      >
                        <div className="flex items-center gap-3 text-sm">
                          <code className="font-mono text-slate-800">{entry.model}</code>
                          <span className="text-slate-500">
                            {t("row.dim", { dimension: entry.dimension })}
                          </span>
                          <span className="text-slate-400 text-xs">
                            {formatRel(entry.created_at)}
                          </span>
                        </div>
                        <DropdownMenu>
                          <DropdownMenuTrigger asChild>
                            <Button size="sm" variant="ghost" className="px-2">
                              <MoreHorizontal className="h-3.5 w-3.5" />
                            </Button>
                          </DropdownMenuTrigger>
                          <DropdownMenuContent align="end">
                            <DropdownMenuItem
                              onSelect={() =>
                                setToDelete({ provider: entry.provider, model: entry.model })
                              }
                              className="text-red-600"
                            >
                              {t("row.delete")}
                            </DropdownMenuItem>
                          </DropdownMenuContent>
                        </DropdownMenu>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}
        </div>
      )}

      <AddModelDialog open={addOpen} onOpenChange={setAddOpen} />
      <DeleteModelAlert entry={toDelete} onClose={() => setToDelete(null)} />
    </div>
  );
}
