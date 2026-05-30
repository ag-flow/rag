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
import { useUpdateGitCredential } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface Props {
  vaultId: string;
  keyId: string;
  keyLabel: string;
  host: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReplaceGitKeyDialog({
  vaultId,
  keyId,
  keyLabel,
  host,
  open,
  onOpenChange,
}: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useUpdateGitCredential(vaultId);
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
      toast({ title: t("gitkeys.replaced_toast") });
      handleClose(false);
    } catch {
      toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("gitkeys.replace_dialog_title")}</DialogTitle>
          <DialogDescription>{t("gitkeys.replace_dialog_desc")}</DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.col_host")} / {t("gitkeys.col_key_id")}
            </Label>
            <Input
              value={`${host} / ${keyLabel}`}
              disabled
              className="mt-1 font-mono bg-slate-50 text-slate-400"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_new_value")}
            </Label>
            <Input
              type="password"
              value={newValue}
              onChange={(e) => setNewValue(e.target.value)}
              placeholder="ghp_…"
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("gitkeys.cancel")}
            </Button>
            <Button type="submit" disabled={mutation.isPending || !newValue.trim()}>
              {t("gitkeys.replace")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
