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
import { useUpdateUserApiKey } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { ScopeSelector } from "./ScopeSelector";
import { RequireOboToggle } from "./RequireOboToggle";
import type { KeyScope, UserApiKey, UserApiKeyUpdate } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

export function EditScopeDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const updateMutation = useUpdateUserApiKey();

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
      // Un seul PATCH, champs modifiés seulement : le serveur applique tout ou
      // rien — deux appels pouvaient changer le niveau sans activer l'OBO.
      const payload: UserApiKeyUpdate = {};
      if (scope !== apiKey.scope) payload.scope = scope;
      if (requireObo !== apiKey.require_obo) payload.require_obo = requireObo;
      if (Object.keys(payload).length > 0) {
        await updateMutation.mutateAsync({ keyId: apiKey.id, payload });
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
            disabled={updateMutation.isPending}
          >
            {t("scope.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
