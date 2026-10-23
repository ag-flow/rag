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
import {
  useCancelReconnect,
  useConfirmReconnect,
  usePendingReconnect,
} from "@/hooks/useHarpocrateReconnect";
import { useToast } from "@/hooks/useToast";

interface ConfirmWalletChangeDialogProps {
  /** Demande en attente (paramètre `request` du retour) ; null : dialogue fermé. */
  requestId: string | null;
  onDone: () => void;
}

/**
 * Retour d'une reconnexion qui change de wallet : rien n'est enregistré tant
 * que l'admin n'a pas confirmé, car les références de secrets existantes
 * pointeraient vers un autre wallet. Fermer le dialogue vaut refus — on ne
 * laisse pas une clé obtenue en attente sans décision.
 */
export function ConfirmWalletChangeDialog({ requestId, onDone }: ConfirmWalletChangeDialogProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const pending = usePendingReconnect(requestId);
  const confirm = useConfirmReconnect();
  const cancel = useCancelReconnect();
  const busy = confirm.isPending || cancel.isPending;

  async function handleConfirm() {
    if (!requestId) return;
    try {
      const { tested } = await confirm.mutateAsync(requestId);
      toast(
        tested
          ? { title: t("connect.reconnected_toast") }
          : { title: t("connect.reconnected_untested_toast"), variant: "destructive" },
      );
    } catch {
      toast({ title: t("reconnect.confirm_error"), variant: "destructive" });
    }
    onDone();
  }

  async function handleRefuse() {
    if (!requestId) return;
    try {
      await cancel.mutateAsync(requestId);
      toast({ title: t("reconnect.refused_toast") });
    } catch {
      // Demande déjà résolue ou expirée : l'ancienne clé est restée de toute façon.
      toast({ title: t("reconnect.refused_toast") });
    }
    onDone();
  }

  const data = pending.data;
  return (
    <Dialog
      open={requestId !== null}
      onOpenChange={(next) => {
        if (!next && !busy) void handleRefuse();
      }}
    >
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("reconnect.confirm_title")}</DialogTitle>
          <DialogDescription>{t("reconnect.confirm_explanation")}</DialogDescription>
        </DialogHeader>
        {pending.isError && (
          <p role="alert" className="text-sm font-medium text-rose-600">
            {t("reconnect.pending_gone")}
          </p>
        )}
        {data && (
          <dl className="space-y-1 text-sm">
            <dt className="text-xs uppercase tracking-wider text-slate-600">
              {t("reconnect.vault")}
            </dt>
            <dd className="font-mono">{data.vault_name}</dd>
            <dt className="text-xs uppercase tracking-wider text-slate-600">
              {t("reconnect.previous_wallet")}
            </dt>
            <dd className="break-all font-mono">
              {data.previous_wallet_id ?? t("reconnect.previous_wallet_unknown")}
            </dd>
            <dt className="text-xs uppercase tracking-wider text-slate-600">
              {t("reconnect.new_wallet")}
            </dt>
            <dd className="break-all font-mono">{data.new_wallet_id}</dd>
          </dl>
        )}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={handleRefuse} disabled={busy}>
            {t("reconnect.refuse")}
          </Button>
          <Button type="button" onClick={handleConfirm} disabled={busy || !data}>
            {t("reconnect.confirm")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
