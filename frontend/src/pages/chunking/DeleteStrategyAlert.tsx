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
import { useDeleteStrategy } from "@/hooks/useChunkingStrategies";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { StrategyOut } from "@/lib/chunking-strategies.types";

interface Props {
  strategy: StrategyOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DeleteStrategyAlert({ strategy, open, onOpenChange }: Props) {
  const { t } = useTranslation("chunking_strategies");
  const { toast } = useToast();
  const remove = useDeleteStrategy();

  async function handleConfirm() {
    try {
      await remove.mutateAsync(strategy.id);
      toast({ title: t("toasts.deleted") });
      onOpenChange(false);
    } catch (err) {
      const title =
        err instanceof ApiError && err.status === 409 ? t("errors.in_use") : t("errors.generic");
      toast({ title, variant: "destructive" });
    }
  }

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{t("delete.title", { label: strategy.label })}</AlertDialogTitle>
          <AlertDialogDescription>{t("delete.description")}</AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>{t("delete.cancel")}</AlertDialogCancel>
          <AlertDialogAction
            className="bg-red-600 hover:bg-red-700"
            onClick={() => void handleConfirm()}
            disabled={remove.isPending}
          >
            {t("delete.confirm")}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
