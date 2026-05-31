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
import { useEnableWebhook } from "@/hooks/useSourceWebhooks";
import { useToast } from "@/hooks/useToast";
import type { WebhookEnableResponse } from "@/lib/source-webhooks.types";

interface Props {
  workspaceName: string;
  sourceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function EnableWebhookDialog({
  workspaceName,
  sourceName,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("git_webhooks");
  const { toast } = useToast();
  const mutation = useEnableWebhook(workspaceName);
  const [result, setResult] = useState<WebhookEnableResponse | null>(null);
  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setResult(null);
      setCopiedUrl(false);
      setCopiedSecret(false);
    }
  }

  async function handleConfirm() {
    try {
      const res = await mutation.mutateAsync(sourceName);
      setResult(res);
    } catch {
      toast({ title: t("enable_error"), variant: "destructive" });
    }
  }

  async function copy(text: string, setCopied: (v: boolean) => void) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("enable_dialog_title")}</DialogTitle>
        </DialogHeader>
        {!result ? (
          <>
            <p className="text-sm text-slate-600">{t("content_type_hint")}</p>
            <DialogFooter>
              <Button variant="outline" onClick={() => handleClose(false)}>
                {t("cancel")}
              </Button>
              <Button onClick={handleConfirm} disabled={mutation.isPending}>
                {t("confirm")}
              </Button>
            </DialogFooter>
          </>
        ) : (
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("url_label")}
              </Label>
              <div className="flex items-center gap-2 mt-1">
                <Input
                  value={result.webhook_url}
                  readOnly
                  className="font-mono text-xs bg-slate-50"
                />
                <Button
                  size="sm"
                  onClick={() => copy(result.webhook_url, setCopiedUrl)}
                  className="shrink-0"
                >
                  {copiedUrl ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-500">
                {t("secret_label")}
              </Label>
              <p className="text-xs text-amber-600 mt-1">{t("secret_warning")}</p>
              <div className="flex items-center gap-2 mt-1">
                <Input
                  value={result.secret}
                  readOnly
                  className="font-mono text-xs bg-slate-50"
                />
                <Button
                  size="sm"
                  onClick={() => copy(result.secret, setCopiedSecret)}
                  className="shrink-0"
                >
                  {copiedSecret ? (
                    <Check className="h-4 w-4" />
                  ) : (
                    <Copy className="h-4 w-4" />
                  )}
                </Button>
              </div>
            </div>
            <p className="text-xs text-slate-500">{t("content_type_hint")}</p>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>{t("close")}</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
