import { useTranslation } from "react-i18next";
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
import { useDeleteWorkspace } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceDeleteAlert({ workspace, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const deleteMutation = useDeleteWorkspace();

  async function handleDelete() {
    try {
      await deleteMutation.mutateAsync(workspace.name);
      toast({ title: t("toasts.deleted", { name: workspace.name }) });
      onOpenChange(false);
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>
            ⚠ {t("delete_dialog.title", { name: workspace.name })}
          </AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div>
              <p className="mb-2">{t("delete_dialog.irreversible")}</p>
              <ul className="list-disc pl-5 text-sm space-y-1 text-slate-700">
                <li>{t("delete_dialog.consequences.db", { name: workspace.name })}</li>
                <li>{t("delete_dialog.consequences.docs", { count: workspace.documents_count })}</li>
                <li>{t("delete_dialog.consequences.apikey")}</li>
                <li>{t("delete_dialog.consequences.agents")}</li>
              </ul>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("common:buttons.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleDelete}
            disabled={deleteMutation.isPending}
            className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
          >
            {t("delete_dialog.confirm_button")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
