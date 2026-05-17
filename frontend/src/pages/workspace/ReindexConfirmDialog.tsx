import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { useReindex } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function ReindexConfirmDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const reindex = useReindex(name);

  const handleConfirm = () => {
    reindex.mutate(undefined, {
      onSuccess: () => {
        toast({ title: t("dialog.reindex.success") });
        onOpenChange(false);
      },
      onError: () =>
        toast({ title: t("dialog.reindex.error"), variant: "destructive" }),
    });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dialog.reindex.title")}</DialogTitle>
        </DialogHeader>
        <div className="flex gap-3 items-start rounded-md bg-amber-50 border border-amber-200 px-4 py-3">
          <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
          <p className="text-sm text-amber-900">{t("dialog.reindex.warning")}</p>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            {t("dialog.cancel")}
          </Button>
          <Button onClick={handleConfirm} disabled={reindex.isPending}>
            {t("dialog.reindex.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
