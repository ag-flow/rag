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
import { useSetUserApiKeyScope } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { ScopeSelector } from "./ScopeSelector";
import type { KeyScope, UserApiKey } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

export function EditScopeDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const setScopeMutation = useSetUserApiKeyScope();

  const [scope, setScope] = useState<KeyScope>("read");

  // Pré-remplit le niveau quand une clé est sélectionnée.
  useEffect(() => {
    if (apiKey) setScope(apiKey.scope);
  }, [apiKey]);

  async function handleSave() {
    if (!apiKey) return;
    try {
      await setScopeMutation.mutateAsync({ keyId: apiKey.id, scope });
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
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={setScopeMutation.isPending}
          >
            {t("scope.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
