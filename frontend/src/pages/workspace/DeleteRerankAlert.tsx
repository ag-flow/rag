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
import { useDeleteRerankConfig } from "@/hooks/useRerank";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function DeleteRerankAlert({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const del = useDeleteRerankConfig(name);

  const handleConfirm = () => {
    del.mutate(undefined, {
      onSuccess: () => {
        toast({ title: t("rerank.delete.success") });
        onOpenChange(false);
      },
      onError: () =>
        toast({ title: t("rerank.delete.error"), variant: "destructive" }),
    });
  };

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("rerank.delete.title")}</AlertDialogTitle>
          <AlertDialogDescription>
            {t("rerank.delete.warning")}
            <br />
            <span className="mt-2 inline-block text-slate-500">
              {t("rerank.delete.reversibleNote")}
            </span>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("dialog.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            onClick={handleConfirm}
            className="bg-red-600 hover:bg-red-700"
          >
            {t("rerank.delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
