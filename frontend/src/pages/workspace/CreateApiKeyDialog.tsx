import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import type { ApiKeyCreated } from "@/lib/workspace-apikeys.types";

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateApiKeyDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const mutation = useCreateApiKey(workspaceName);
  const [name, setName] = useState("");
  const [created, setCreated] = useState<ApiKeyCreated | null>(null);
  const [copied, setCopied] = useState(false);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setName(""); setCreated(null); setCopied(false); }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;
    try {
      const result = await mutation.mutateAsync({ name: name.trim() });
      setCreated(result);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  async function handleCopy() {
    if (!created) return;
    await navigator.clipboard.writeText(created.api_key);
    setCopied(true);
    toast({ title: t("copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("create_dialog_title")}</DialogTitle>
        </DialogHeader>

        {!created ? (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("field_name_placeholder")}
                className="mt-1"
                autoFocus
              />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("cancel")}
              </Button>
              <Button type="submit" disabled={!name.trim() || mutation.isPending}>
                {t("create_save")}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-4">
            <div>
              <p className="text-sm font-semibold text-slate-900">{t("created_key_title")}</p>
              <p className="mt-1 text-xs text-amber-600">{t("created_key_warning")}</p>
            </div>
            <div className="flex items-center gap-2">
              <Input
                value={created.api_key}
                readOnly
                className="font-mono text-xs bg-slate-50"
              />
              <Button type="button" size="sm" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
              </Button>
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
