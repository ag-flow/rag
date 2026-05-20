import { useTranslation } from "react-i18next";
import { MoreHorizontal, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  onReindex: () => void;
  onReveal: () => void;
  onRotate: () => void;
  onDelete: () => void;
}

function relativeTimeRaw(iso: string): { key: string; count: number } {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return { key: "time.justNow", count: 0 };
  if (minutes < 60) return { key: "time.minutesAgo", count: minutes };
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return { key: "time.hoursAgo", count: hours };
  return { key: "time.daysAgo", count: Math.floor(hours / 24) };
}

export function WorkspaceHeader({ workspace, onReindex, onReveal, onRotate, onDelete }: Props) {
  const { t } = useTranslation("workspace");
  return (
    <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 bg-white sticky top-0 z-10">
      <div>
        <h2 className="text-xl font-semibold text-slate-900">{workspace.name}</h2>
        <p className="text-xs text-slate-500">
          {(() => {
            const rel = relativeTimeRaw(workspace.created_at);
            const when =
              rel.key === "time.justNow" ? t("time.justNow") : t(rel.key, { count: rel.count });
            return t("header.created", { when });
          })()}
        </p>
      </div>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="outline" onClick={onReindex}>
          <RefreshCw className="h-4 w-4" /> {t("header.reindex")}
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button size="sm" variant="ghost" className="px-2">
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onSelect={onReveal}>{t("header.menu.reveal")}</DropdownMenuItem>
            <DropdownMenuItem onSelect={onRotate}>{t("header.menu.rotate")}</DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={onDelete} className="text-red-600">
              {t("header.menu.delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </div>
  );
}
