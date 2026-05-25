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
import { useToast } from "@/hooks/useToast";
import { useDeleteModel } from "@/hooks/useModels";

interface Props {
  entry: { provider: string; model: string } | null;
  onClose: () => void;
}

export function DeleteModelAlert({ entry, onClose }: Props) {
  const { t } = useTranslation("models");
  const { toast } = useToast();
  const del = useDeleteModel();

  const open = entry !== null;

  const handleConfirm = () => {
    if (!entry) return;
    del.mutate(entry, {
      onSuccess: () => {
        toast({ title: t("dialog.delete.success") });
        onClose();
      },
      onError: () => toast({ title: t("dialog.delete.error"), variant: "destructive" }),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("dialog.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {entry &&
              t("dialog.delete.warning", {
                provider: entry.provider,
                model: entry.model,
              })}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            disabled={del.isPending}
            className="bg-red-600 hover:bg-red-700"
          >
            {t("dialog.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
