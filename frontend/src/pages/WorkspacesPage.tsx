import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, FolderOpen } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { WorkspaceCreateDialog } from "@/pages/WorkspaceCreateDialog";
import { WorkspaceActions } from "@/pages/WorkspaceActions";

function formatRelative(iso: string): string {
  const date = new Date(iso);
  const diffMs = Date.now() - date.getTime();
  const minutes = Math.floor(diffMs / 60_000);
  if (minutes < 1) return "à l'instant";
  if (minutes < 60) return `il y a ${minutes} min`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `il y a ${hours} h`;
  const days = Math.floor(hours / 24);
  return `il y a ${days} j`;
}

function EmptyState({ onCreate }: { onCreate: () => void }) {
  const { t } = useTranslation("workspaces");
  return (
    <div className="mx-auto mt-16 max-w-md text-center rounded-lg border border-dashed border-slate-300 p-10">
      <FolderOpen className="mx-auto mb-3 h-10 w-10 text-slate-400" />
      <h3 className="text-base font-semibold text-slate-900 mb-1.5">
        {t("empty.title")}
      </h3>
      <p className="text-sm text-slate-500 mb-5">{t("empty.description")}</p>
      <Button onClick={onCreate}>
        <Plus className="h-4 w-4" />
        {t("create")}
      </Button>
    </div>
  );
}

export function WorkspacesPage() {
  const { t } = useTranslation("workspaces");
  const { data, isLoading } = useWorkspaces();
  const [createOpen, setCreateOpen] = useState(false);

  if (isLoading) return <LoadingSpinner />;

  const workspaces = data ?? [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold tracking-tight">{t("title")}</h2>
        <Button onClick={() => setCreateOpen(true)}>
          <Plus className="h-4 w-4" />
          {t("create")}
        </Button>
      </div>

      {workspaces.length === 0 ? (
        <EmptyState onCreate={() => setCreateOpen(true)} />
      ) : (
        <div className="rounded-md border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("table.name")}</TableHead>
                <TableHead>{t("table.indexer")}</TableHead>
                <TableHead>{t("table.sources")}</TableHead>
                <TableHead>{t("table.documents")}</TableHead>
                <TableHead>{t("table.last_indexed")}</TableHead>
                <TableHead className="w-10" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {workspaces.map((ws) => (
                <TableRow key={ws.id}>
                  <TableCell className="font-medium">{ws.name}</TableCell>
                  <TableCell>
                    <Badge variant="secondary" className="font-mono text-xs">
                      {ws.indexer.provider}/{ws.indexer.model}
                    </Badge>
                  </TableCell>
                  <TableCell>{ws.sources_count}</TableCell>
                  <TableCell>{ws.documents_count}</TableCell>
                  <TableCell className="text-muted-foreground">
                    {ws.last_indexed_at
                      ? formatRelative(ws.last_indexed_at)
                      : t("table.never")}
                  </TableCell>
                  <TableCell>
                    <WorkspaceActions workspace={ws} />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <WorkspaceCreateDialog open={createOpen} onOpenChange={setCreateOpen} />
    </div>
  );
}
