import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
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
import { useUpdateProviderKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface Props {
  vaultId: string;
  keyId: string;
  keyLabel: string;
  provider: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReplaceProviderKeyDialog({
  vaultId,
  keyId,
  keyLabel,
  provider,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useUpdateProviderKey(vaultId);
  const [newValue, setNewValue] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setNewValue("");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newValue.trim()) return;
    try {
      await mutation.mutateAsync({ keyId, payload: { value: newValue } });
      toast({ title: t("apikeys.replaced_toast") });
      handleClose(false);
    } catch {
      toast({ title: t("apikeys.error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("apikeys.replace_dialog_title")}</DialogTitle>
          <DialogDescription>{t("apikeys.replace_dialog_desc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.col_provider")} / {t("apikeys.col_key_id")}
            </Label>
            <Input
              value={`${provider} / ${keyLabel}`}
              disabled
              className="mt-1 font-mono bg-slate-50 text-slate-400"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_new_value")}
            </Label>
            <Input
              type="password"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="sk-…"
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("apikeys.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || !newValue.trim()}
            >
              {t("apikeys.replace")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
