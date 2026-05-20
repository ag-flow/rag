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

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  current: string;
  next: string;
  onConfirm: () => void;
  pending: boolean;
}

export function ChunkingConfirmReindexAlert({
  open,
  onOpenChange,
  current,
  next,
  onConfirm,
  pending,
}: Props) {
  const { t } = useTranslation("workspace");

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("chunking.reindex.dialog.title")}</AlertDialogTitle>
          <AlertDialogDescription asChild>
            <div className="space-y-2 text-sm">
              <p>{t("chunking.reindex.dialog.intro")}</p>
              <p>
                <span className="font-medium">{t("chunking.reindex.dialog.labelCurrent")}</span>
                <br />
                <span className="font-mono text-slate-700">{current}</span>
              </p>
              <p>
                <span className="font-medium">{t("chunking.reindex.dialog.labelNew")}</span>
                <br />
                <span className="font-mono text-slate-700">{next}</span>
              </p>
              <p className="text-slate-500">{t("chunking.reindex.dialog.consequence")}</p>
            </div>
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel disabled={pending}>
            {t("chunking.reindex.dialog.actions.cancel")}
          </AlertDialogCancel>
          <AlertDialogAction
            onClick={onConfirm}
            disabled={pending}
            className="bg-amber-600 hover:bg-amber-700"
          >
            {t("chunking.reindex.dialog.actions.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
