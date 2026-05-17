import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle, Copy, Eye, EyeOff } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRevealApiKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface RevealApiKeyDialogProps {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RevealApiKeyDialog({
  vaultId,
  open,
  onOpenChange,
}: RevealApiKeyDialogProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useRevealApiKey(vaultId);

  const [revealed, setRevealed] = useState<{ id: string; key: string } | null>(
    null,
  );
  const [visible, setVisible] = useState(false);

  // Reset complet à la fermeture : aucune valeur ne doit persister en mémoire.
  useEffect(() => {
    if (!open) {
      setRevealed(null);
      setVisible(false);
    }
  }, [open]);

  async function handleConfirm() {
    try {
      const result = await mutation.mutateAsync();
      setRevealed({ id: result.api_key_id, key: result.api_key });
    } catch {
      toast({
        title: t("reveal_dialog.error_toast"),
        variant: "destructive",
      });
    }
  }

  async function handleCopy() {
    if (!revealed) return;
    try {
      await navigator.clipboard.writeText(revealed.key);
      toast({ title: t("reveal_dialog.copied_toast") });
    } catch {
      // Clipboard peut être refusé (contexte non-secure). On affiche quand même
      // un toast neutre pour signaler que l'action a été tentée.
      toast({ title: t("reveal_dialog.copied_toast") });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        {!revealed ? (
          <>
            <DialogHeader>
              <DialogTitle>{t("reveal_dialog.title")}</DialogTitle>
            </DialogHeader>
            <div className="rounded border border-amber-300 bg-amber-50 p-3 flex gap-3">
              <AlertTriangle className="h-5 w-5 text-amber-600 flex-shrink-0 mt-0.5" />
              <div>
                <p className="font-semibold text-amber-800 text-sm mb-1">
                  {t("reveal_dialog.warning_title")}
                </p>
                <p className="text-sm text-amber-700 leading-relaxed">
                  {t("reveal_dialog.warning_body")}
                </p>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t("reveal_dialog.cancel")}
              </Button>
              <Button onClick={handleConfirm} disabled={mutation.isPending}>
                {t("reveal_dialog.confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("reveal_dialog.title")}</DialogTitle>
              <DialogDescription className="sr-only">
                {t("reveal_dialog.warning_title")}
              </DialogDescription>
            </DialogHeader>
            <div className="space-y-4">
              <div>
                <Label className="text-xs uppercase tracking-wider text-slate-600">
                  {t("reveal_dialog.revealed_id_label")}
                </Label>
                <Input
                  value={revealed.id}
                  readOnly
                  className="mt-1 font-mono bg-slate-50"
                />
              </div>
              <div>
                <Label className="text-xs uppercase tracking-wider text-slate-600">
                  {t("reveal_dialog.revealed_key_label")}
                </Label>
                <div className="mt-1 flex items-center gap-2">
                  <Input
                    type={visible ? "text" : "password"}
                    value={revealed.key}
                    readOnly
                    className="flex-1 font-mono bg-slate-50"
                  />
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={() => setVisible((v) => !v)}
                    aria-label={
                      visible
                        ? t("reveal_dialog.hide")
                        : t("reveal_dialog.show")
                    }
                  >
                    {visible ? (
                      <EyeOff className="h-4 w-4" />
                    ) : (
                      <Eye className="h-4 w-4" />
                    )}
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="icon"
                    onClick={handleCopy}
                    aria-label={t("reveal_dialog.copy")}
                  >
                    <Copy className="h-4 w-4" />
                  </Button>
                </div>
              </div>
            </div>
            <DialogFooter>
              <Button variant="outline" onClick={() => onOpenChange(false)}>
                {t("reveal_dialog.close")}
              </Button>
            </DialogFooter>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}
