import { useEffect, useState } from "react";
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
import { useSetUserApiKeyRequireObo, useSetUserApiKeyScope } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { ScopeSelector } from "./ScopeSelector";
import { RequireOboToggle } from "./RequireOboToggle";
import type { KeyScope, UserApiKey } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

export function EditScopeDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const setScopeMutation = useSetUserApiKeyScope();
  const setRequireOboMutation = useSetUserApiKeyRequireObo();

  const [scope, setScope] = useState<KeyScope>("read");
  const [requireObo, setRequireObo] = useState(false);

  // Pré-remplit niveau et exigence OBO quand une clé est sélectionnée.
  useEffect(() => {
    if (apiKey) {
      setScope(apiKey.scope);
      setRequireObo(apiKey.require_obo);
    }
  }, [apiKey]);

  async function handleSave() {
    if (!apiKey) return;
    try {
      // Deux routes distinctes côté API : on n'appelle que celle qui change.
      if (scope !== apiKey.scope) {
        await setScopeMutation.mutateAsync({ keyId: apiKey.id, scope });
      }
      if (requireObo !== apiKey.require_obo) {
        await setRequireOboMutation.mutateAsync({ keyId: apiKey.id, requireObo });
      }
      toast({ title: t("scope.saved_toast") });
      onOpenChange(false);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={apiKey !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("scope.edit_title", { name: apiKey?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("scope.help")}</DialogDescription>
        </DialogHeader>
        <ScopeSelector value={scope} onChange={setScope} />
        <RequireOboToggle checked={requireObo} onChange={setRequireObo} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={setScopeMutation.isPending || setRequireOboMutation.isPending}
          >
            {t("scope.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
