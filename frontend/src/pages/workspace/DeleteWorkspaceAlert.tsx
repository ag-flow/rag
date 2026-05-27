import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
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
import { Input } from "@/components/ui/input";
import { useDeleteWorkspace } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function DeleteWorkspaceAlert({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const navigate = useNavigate();
  const del = useDeleteWorkspace();
  const [confirmText, setConfirmText] = useState("");

  useEffect(() => {
    if (!open) setConfirmText("");
  }, [open]);

  const handleConfirm = () => {
    del.mutate(name, {
      onSuccess: () => {
        toast({ title: t("dialog.delete.success") });
        onOpenChange(false);
        navigate("/workspaces", { replace: true });
      },
      onError: () => toast({ title: t("dialog.delete.error"), variant: "destructive" }),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("dialog.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("dialog.delete.warning")}</AlertDialogDescription>
        </AlertDialogHeader>
        <div>
          <label className="text-xs font-medium text-slate-700">
            {t("dialog.delete.confirmLabel", { name })}
          </label>
          <Input
            value={confirmText}
            onChange={(e) => setConfirmText(e.target.value)}
            placeholder={name}
          />
        </div>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={confirmText !== name || del.isPending}
            className="bg-red-600 hover:bg-red-700"
          >
            {t("dialog.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
