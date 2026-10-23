import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { useReconnectStart } from "@/hooks/useHarpocrateReconnect";
import { parseStartError, type Declaration } from "@/pages/harpocrate/connectStartError";
import { DeclarationDetails } from "@/pages/harpocrate/DeclarationDetails";

interface ReconnectVaultDialogProps {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/**
 * « Reconnecter » : renouvelle la clé du coffre par le parcours Harpocrate.
 * Le rappel avant départ est une exigence du ticket : la clé obtenue
 * appartient au compte Harpocrate de qui consent, alors que les coffres sont
 * partagés entre admins.
 */
export function ReconnectVaultDialog({ vaultId, open, onOpenChange }: ReconnectVaultDialogProps) {
  const { t } = useTranslation("harpocrate");
  const start = useReconnectStart(vaultId);
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [declaration, setDeclaration] = useState<Declaration | null>(null);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setErrorKey(null);
      setDeclaration(null);
    }
  }

  async function handleReconnect() {
    setErrorKey(null);
    setDeclaration(null);
    try {
      const { browser_url } = await start.mutateAsync();
      window.location.assign(browser_url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        setErrorKey("harpocrate_dek_missing");
        return;
      }
      const parsed = parseStartError(err);
      setErrorKey(parsed.key);
      setDeclaration(parsed.declaration);
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("reconnect.title")}</DialogTitle>
          <DialogDescription>{t("reconnect.explanation")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          <p className="text-sm text-slate-600">{t("reconnect.owner_warning")}</p>
          <p className="text-sm text-slate-600">{t("reconnect.old_key_note")}</p>
          {errorKey && (
            <p role="alert" className="text-sm font-medium text-rose-600">
              {t(`connect.errors.${errorKey}`)}
            </p>
          )}
          {declaration && <DeclarationDetails declaration={declaration} />}
        </div>
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => handleClose(false)}>
            {t("reconnect.cancel")}
          </Button>
          <Button type="button" onClick={handleReconnect} disabled={start.isPending}>
            <Link2 className="mr-2 h-4 w-4" />
            {start.isPending ? t("connect.starting") : t("reconnect.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
