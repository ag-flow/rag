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
import { useReplaceApiKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";

interface ReplaceApiKeyDialogProps {
  vaultId: string;
  currentApiKeyId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ReplaceApiKeyDialog({
  vaultId,
  currentApiKeyId,
  open,
  onOpenChange,
}: ReplaceApiKeyDialogProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useReplaceApiKey(vaultId);
  const [newId, setNewId] = useState("");
  const [newKey, setNewKey] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setNewId("");
      setNewKey("");
    }
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!newId || newKey.length < 8) return;
    try {
      await mutation.mutateAsync({ api_key_id: newId, api_key: newKey });
      toast({ title: t("replace_dialog.replaced_toast") });
      handleClose(false);
    } catch {
      toast({
        title: t("replace_dialog.error_toast"),
        variant: "destructive",
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("replace_dialog.title")}</DialogTitle>
          <DialogDescription>
            {t("replace_dialog.explanation")}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("replace_dialog.current_label")}
            </Label>
            <Input
              value={currentApiKeyId}
              disabled
              className="mt-1 font-mono bg-slate-50 text-slate-400"
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("replace_dialog.new_id_label")}
            </Label>
            <Input
              value={newId}
              onChange={(e) => setNewId(e.target.value)}
              placeholder={t("replace_dialog.new_id_placeholder")}
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("replace_dialog.new_key_label")}
            </Label>
            <Input
              type="password"
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder={t("replace_dialog.new_key_placeholder")}
              className="mt-1 font-mono"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => handleClose(false)}
            >
              {t("replace_dialog.cancel")}
            </Button>
            <Button
              type="submit"
              disabled={mutation.isPending || !newId || newKey.length < 8}
            >
              {t("replace_dialog.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
