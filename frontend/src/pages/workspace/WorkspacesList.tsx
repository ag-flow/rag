import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import type { Workspace } from "@/lib/workspaces.types";

interface WorkspacesListProps {
  selectedName: string | null;
  onSelect: (name: string) => void;
  onCreate: () => void;
}

export function WorkspacesList({ selectedName, onSelect, onCreate }: WorkspacesListProps) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useWorkspaces();

  return (
    <aside className="w-[240px] flex-shrink-0 border-r border-slate-200 bg-white">
      <div className="flex items-center justify-between px-4 py-3 border-b border-slate-100">
        <span className="font-semibold text-slate-900">{t("list.header")}</span>
        <Button size="sm" onClick={onCreate} className="h-7 px-2.5 text-xs">
          {t("list.new")}
        </Button>
      </div>
      <div className="py-2">
        {isLoading ? (
          <div className="px-4 py-6 flex justify-center"><LoadingSpinner /></div>
        ) : (
          (data ?? []).map((ws: Workspace) => (
            <button
              key={ws.id}
              type="button"
              onClick={() => onSelect(ws.name)}
              className={cn(
                "w-full text-left px-4 py-2 hover:bg-slate-50",
                ws.name === selectedName && "bg-blue-50 hover:bg-blue-100",
              )}
            >
              <div className="font-medium text-sm text-slate-900">{ws.name}</div>
              <div className="text-xs text-slate-500">
                {ws.indexer.provider}/{ws.indexer.model} · {ws.documents_count} docs
              </div>
            </button>
          ))
        )}
      </div>
    </aside>
  );
}
