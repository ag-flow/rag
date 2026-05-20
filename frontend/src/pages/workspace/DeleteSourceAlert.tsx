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
import { useDeleteSource } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  sourceId: string | null;
  onClose: () => void;
}

export function DeleteSourceAlert({ name, sourceId, onClose }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const del = useDeleteSource(name);
  const open = sourceId !== null;

  const handleConfirm = () => {
    if (!sourceId) return;
    del.mutate(sourceId, {
      onSuccess: () => {
        toast({ title: t("sources.delete.success") });
        onClose();
      },
      onError: () => toast({ title: t("sources.delete.error"), variant: "destructive" }),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={(o) => !o && onClose()}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("sources.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>{t("sources.delete.warning")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} className="bg-red-600 hover:bg-red-700">
            {t("sources.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
