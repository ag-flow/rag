import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useRotateWebhookSecret } from "@/hooks/useSourceWebhooks";
import { useToast } from "@/hooks/useToast";

interface Props {
  workspaceName: string;
  sourceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RotateWebhookSecretDialog({
  workspaceName,
  sourceName,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("git_webhooks");
  const { toast } = useToast();
  const mutation = useRotateWebhookSecret(workspaceName);
  const [newSecret, setNewSecret] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setNewSecret(null);
      setCopied(false);
    }
  }

  async function handleRotate() {
    try {
      const res = await mutation.mutateAsync(sourceName);
      setNewSecret(res.secret);
    } catch {
      toast({ title: t("rotate_error"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!newSecret) return;
    await navigator.clipboard.writeText(newSecret);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("rotate_dialog_title")}</DialogTitle>
        </DialogHeader>
        {!newSecret ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button onClick={handleRotate} disabled={mutation.isPending}>
              {t("confirm")}
            </Button>
          </DialogFooter>
        ) : (
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("rotate_new_secret_label")}
              </Label>
              <p className="text-xs text-amber-600 mt-1">{t("secret_warning")}</p>
              <div className="flex items-center gap-2 mt-1">
                <Input
                  value={newSecret}
                  readOnly
                  className="font-mono text-xs bg-slate-50"
                />
                <Button size="sm" onClick={handleCopy} className="shrink-0">
                  {copied ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>{t("close")}</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
