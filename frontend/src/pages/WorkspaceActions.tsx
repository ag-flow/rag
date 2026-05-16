import { useState } from "react";
import { useTranslation } from "react-i18next";
import { MoreVertical, KeyRound, RotateCw, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { WorkspaceDeleteAlert } from "@/pages/WorkspaceDeleteAlert";
import { useRotateApiKey, useReindex } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";
import type { Workspace } from "@/lib/validators";

export function WorkspaceActions({ workspace }: { workspace: Workspace }) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const [deleteOpen, setDeleteOpen] = useState(false);
  const rotateMutation = useRotateApiKey();
  const reindexMutation = useReindex();

  async function handleRotate() {
    try {
      const resp = await rotateMutation.mutateAsync(workspace.name);
      toast({
        title: t("toasts.apikey_rotated", { name: workspace.name }),
        description: resp.api_key,
        duration: 30_000,
      });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  async function handleReindex() {
    try {
      await reindexMutation.mutateAsync(workspace.name);
      toast({ title: t("toasts.reindex_started", { name: workspace.name }) });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-7 w-7">
            <MoreVertical className="h-4 w-4" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem onClick={handleRotate}>
            <KeyRound className="h-4 w-4 mr-2" />
            {t("actions.rotate_apikey")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={handleReindex}>
            <RotateCw className="h-4 w-4 mr-2" />
            {t("actions.reindex")}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onClick={() => setDeleteOpen(true)}
            className="text-destructive focus:text-destructive"
          >
            <Trash2 className="h-4 w-4 mr-2" />
            {t("actions.delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>

      <WorkspaceDeleteAlert
        workspace={workspace}
        open={deleteOpen}
        onOpenChange={setDeleteOpen}
      />
    </>
  );
}
