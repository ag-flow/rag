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
import { useRevealApiKey } from "@/hooks/useWorkspaces";
import { useToast } from "@/hooks/useToast";

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function RevealApiKeyDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const reveal = useRevealApiKey(name);
  const [revealed, setRevealed] = useState<string | null>(null);

  // Auto-mask après 30s.
  useEffect(() => {
    if (!revealed) return;
    const id = setTimeout(() => setRevealed(null), 30_000);
    return () => clearTimeout(id);
  }, [revealed]);

  // Reset à la fermeture.
  useEffect(() => {
    if (!open) setRevealed(null);
  }, [open]);

  const handleConfirm = () => {
    reveal.mutate(undefined, {
      onSuccess: (data) => setRevealed(data.api_key),
      onError: () => toast({ title: t("dialog.reveal.error"), variant: "destructive" }),
    });
  };

  const handleCopy = () => {
    if (!revealed) return;
    void navigator.clipboard.writeText(revealed);
    toast({ title: t("dialog.reveal.copied") });
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dialog.reveal.title")}</DialogTitle>
        </DialogHeader>
        {revealed === null ? (
          <>
            <div className="flex gap-3 items-start rounded-md bg-amber-50 border border-amber-200 px-4 py-3">
              <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <p className="text-sm text-amber-900">{t("dialog.reveal.warning")}</p>
            </div>
            <DialogFooter>
              <Button variant="ghost" onClick={() => onOpenChange(false)}>
                {t("dialog.cancel")}
              </Button>
              <Button onClick={handleConfirm} disabled={reveal.isPending}>
                {t("dialog.reveal.confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <p className="text-sm text-slate-700">{t("dialog.reveal.copyHint")}</p>
            <div className="flex items-center gap-2 rounded bg-slate-100 px-3 py-2">
              <code className="flex-1 font-mono text-xs break-all">{revealed}</code>
              <Button size="sm" variant="outline" onClick={handleCopy}>
                <Copy className="h-3.5 w-3.5" />
              </Button>
            </div>
            <p className="text-xs text-slate-500">{t("dialog.reveal.autoMaskNote")}</p>
            <DialogFooter>
              <Button onClick={() => onOpenChange(false)}>{t("dialog.close")}</Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
