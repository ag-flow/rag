import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
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
import { useDeleteVault } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface RetireVaultDialogProps {
  vault: VaultSummary;
  walletName: string | null;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onRetired: () => void;
}

export function RetireVaultDialog({
  vault,
  walletName,
  open,
  onOpenChange,
  onRetired,
}: RetireVaultDialogProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useDeleteVault();
  const [typed, setTyped] = useState("");

  useEffect(() => {
    if (!open) setTyped("");
  }, [open]);

  const matches = typed === vault.name;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!matches) return;
    try {
      await mutation.mutateAsync(vault.id);
      toast({
        title: t("retire_dialog.retired_toast", { name: vault.name }),
      });
      onOpenChange(false);
      onRetired();
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({
          title: t("retire_dialog.default_conflict_toast"),
          variant: "destructive",
        });
        return;
      }
      toast({
        title: t("retire_dialog.error_toast"),
        variant: "destructive",
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <div className="flex items-center gap-2.5">
            <AlertTriangle className="h-5 w-5 text-rose-600" />
            <DialogTitle className="text-rose-700">
              {t("retire_dialog.title")}
            </DialogTitle>
          </div>
        </DialogHeader>
        <p className="text-sm text-slate-700 leading-relaxed">
          {walletName
            ? t("retire_dialog.warning_with_wallet", {
                wallet_name: walletName,
                vault_name: vault.name,
              })
            : t("retire_dialog.warning_without_wallet", {
                vault_name: vault.name,
              })}
        </p>
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("retire_dialog.confirm_label")}{" "}
              <span className="font-mono text-slate-900">{vault.name}</span>
            </Label>
            <Input
              value={typed}
              onChange={(e) => setTyped(e.target.value)}
              placeholder={t("retire_dialog.confirm_placeholder", {
                vault_name: vault.name,
              })}
              className="mt-1 font-mono"
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => onOpenChange(false)}
            >
              {t("retire_dialog.cancel")}
            </Button>
            <Button
              type="submit"
              variant="destructive"
              disabled={!matches || mutation.isPending}
            >
              {t("retire_dialog.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
