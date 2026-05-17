import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, AlertTriangle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRotateApiKey } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function RotateApiKeyDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const rotate = useRotateApiKey(name);
  const [confirmText, setConfirmText] = useState("");
  const [newKey, setNewKey] = useState<string | null>(null);

  useEffect(() => {
    if (!open) {
      setConfirmText("");
      setNewKey(null);
    }
  }, [open]);

  const handleConfirm = () => {
    rotate.mutate(undefined, {
      onSuccess: (data) => {
        setNewKey(data.api_key);
        toast({ title: t("dialog.rotate.success") });
      },
      onError: () =>
        toast({ title: t("dialog.rotate.error"), variant: "destructive" }),
    });
  };

  const handleCopy = () => {
    if (!newKey) return;
    void navigator.clipboard.writeText(newKey);
    toast({ title: t("dialog.rotate.copied") });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dialog.rotate.title")}</DialogTitle>
        </DialogHeader>
        {newKey === null ? (
          <>
            <div className="flex gap-3 items-start rounded-md bg-red-50 border border-red-200 px-4 py-3">
              <AlertTriangle className="h-4 w-4 text-red-600 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-red-900">{t("dialog.rotate.warning")}</p>
            </div>
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("dialog.rotate.confirmLabel", { name })}
              </label>
              <Input
                value={confirmText}
                onChange={(e) => setConfirmText(e.target.value)}
                placeholder={name}
              />
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                {t("dialog.cancel")}
              </Button>
              <Button
                onClick={handleConfirm}
                disabled={confirmText !== name || rotate.isPending}
                className="bg-red-600 hover:bg-red-700"
              >
                {t("dialog.rotate.confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700">{t("dialog.rotate.copyHint")}</p>
            <div className="flex items-center gap-2 rounded bg-slate-100 px-3 py-2">
              <code className="flex-1 font-mono text-xs break-all">{newKey}</code>
              <Button size="sm" variant="outline" onClick={handleCopy}>
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
            <p className="text-xs text-amber-700">{t("dialog.rotate.oneTimeWarning")}</p>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>{t("dialog.close")}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
