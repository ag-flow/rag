import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, MoreHorizontal } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useChunkingStrategies } from "@/hooks/useChunkingStrategies";
import type { StrategyOut } from "@/lib/chunking-strategies.types";
import { StrategyFormDialog } from "@/pages/chunking/StrategyFormDialog";
import { RoutesEditorDialog } from "@/pages/chunking/RoutesEditorDialog";
import { DuplicateStrategyDialog } from "@/pages/chunking/DuplicateStrategyDialog";
import { DeleteStrategyAlert } from "@/pages/chunking/DeleteStrategyAlert";

function UsageBadges({ strategy }: { strategy: StrategyOut }) {
  const { t } = useTranslation("chunking_strategies");
  const used = strategy.used_by_routes > 0 || strategy.used_by_categories > 0;
  if (!used) {
    return <span className="text-xs text-slate-400">{t("badges.unused")}</span>;
  }
  return (
    <span className="flex flex-wrap gap-1">
      {strategy.used_by_routes > 0 && (
        <Badge variant="secondary">
          {t("badges.used_by_routes", { count: strategy.used_by_routes })}
        </Badge>
      )}
      {strategy.used_by_categories > 0 && (
        <Badge variant="secondary">
          {t("badges.used_by_categories", { count: strategy.used_by_categories })}
        </Badge>
      )}
    </span>
  );
}

export function ChunkingStrategiesPage() {
  const { t } = useTranslation("chunking_strategies");
  const { data, isLoading } = useChunkingStrategies();
  const [createOpen, setCreateOpen] = useState(false);
  const [toEdit, setToEdit] = useState<StrategyOut | null>(null);
  const [routesFor, setRoutesFor] = useState<StrategyOut | null>(null);
  const [toDuplicate, setToDuplicate] = useState<StrategyOut | null>(null);
  const [toDelete, setToDelete] = useState<StrategyOut | null>(null);

  if (isLoading) return <LoadingSpinner />;
  const strategies = data ?? [];

  return (
    <div className="p-6">
      <div className="mb-4 flex items-start justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
          <p className="text-sm text-slate-500">{t("subtitle")}</p>
        </div>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="mr-1 h-4 w-4" />
          {t("add_btn")}
        </Button>
      </div>

      {strategies.length === 0 ? (
        <p className="text-sm text-slate-500">{t("empty")}</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{t("table.label")}</TableHead>
              <TableHead>{t("table.slug")}</TableHead>
              <TableHead>{t("table.algo")}</TableHead>
              <TableHead>{t("table.parser")}</TableHead>
              <TableHead>{t("table.usage")}</TableHead>
              <TableHead className="w-10" />
            </TableRow>
          </TableHeader>
          <TableBody>
            {strategies.map((s) => (
              <TableRow key={s.id}>
                <TableCell className="font-medium">
                  <span className="flex items-center gap-2">
                    {s.label}
                    {s.is_system && <Badge variant="outline">{t("badges.system")}</Badge>}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-xs text-slate-500">{s.slug}</TableCell>
                <TableCell>{s.algo}</TableCell>
                <TableCell className="text-slate-500">{s.parser_slug ?? "—"}</TableCell>
                <TableCell>
                  <UsageBadges strategy={s} />
                </TableCell>
                <TableCell>
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" aria-label={s.slug}>
                        <MoreHorizontal className="h-4 w-4" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem disabled={s.is_system} onSelect={() => setToEdit(s)}>
                        {t("actions.edit")}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={s.is_system || s.parser_slug === null}
                        onSelect={() => setRoutesFor(s)}
                      >
                        {t("actions.routes")}
                      </DropdownMenuItem>
                      <DropdownMenuItem onSelect={() => setToDuplicate(s)}>
                        {t("actions.duplicate")}
                      </DropdownMenuItem>
                      <DropdownMenuItem
                        disabled={s.is_system}
                        className="text-red-600"
                        onSelect={() => setToDelete(s)}
                      >
                        {t("actions.delete")}
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}

      <StrategyFormDialog open={createOpen} onOpenChange={setCreateOpen} strategy={null} />
      <StrategyFormDialog
        open={toEdit !== null}
        onOpenChange={(open) => !open && setToEdit(null)}
        strategy={toEdit}
      />
      {routesFor !== null && (
        <RoutesEditorDialog
          strategy={routesFor}
          open
          onOpenChange={(open) => !open && setRoutesFor(null)}
        />
      )}
      {toDuplicate !== null && (
        <DuplicateStrategyDialog
          strategy={toDuplicate}
          open
          onOpenChange={(open) => !open && setToDuplicate(null)}
        />
      )}
      {toDelete !== null && (
        <DeleteStrategyAlert
          strategy={toDelete}
          open
          onOpenChange={(open) => !open && setToDelete(null)}
        />
      )}
    </div>
  );
}
