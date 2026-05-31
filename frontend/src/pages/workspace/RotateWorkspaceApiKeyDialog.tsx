import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useRotateApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import type { ApiKeyRotated } from "@/lib/workspace-apikeys.types";

interface Props {
  workspaceName: string;
  keyId: string;
  keyName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function RotateWorkspaceApiKeyDialog({ workspaceName, keyId, keyName, open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const mutation = useRotateApiKey(workspaceName);
  const [rotated, setRotated] = useState<ApiKeyRotated | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setRotated(null); setCopied(false); }
  }

  async function handleRotate() {
    try {
      const result = await mutation.mutateAsync(keyId);
      setRotated(result);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!rotated) return;
    await navigator.clipboard.writeText(rotated.new_api_key);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  const graceDate = rotated
    ? new Date(rotated.grace_until).toLocaleString("fr-FR")
    : "";

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("rotate_dialog_title")}</DialogTitle>
          {!rotated && (
            <DialogDescription>
              <strong>{keyName}</strong> — {t("rotate_confirm")}
            </DialogDescription>
          )}
        </DialogHeader>

        {!rotated ? (
          <DialogFooter>
            <Button variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button onClick={handleRotate} disabled={mutation.isPending}>
              {t("rotate_save")}
            </Button>
          </DialogFooter>
        ) : (
          <div className="space-y-4">
            <p className="text-sm font-semibold text-slate-900">{t("rotated_new_key_title")}</p>
            <p className="text-xs text-amber-600">{t("created_key_warning")}</p>
            <div className="flex items-center gap-2">
              <Input
                value={rotated.new_api_key}
                readOnly
                className="font-mono text-xs bg-slate-50"
              />
              <Button type="button" size="sm" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-xs text-slate-500">
              {t("grace_info", { date: graceDate })}
            </p>
            <DialogFooter>
              <Button onClick={() => handleClose(false)}>{t("close")}</Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
