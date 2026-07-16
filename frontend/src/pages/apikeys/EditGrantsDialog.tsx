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
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { useSetUserApiKeyGrants } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { GrantsEditor } from "./GrantsEditor";
import type { UserApiKey, WorkspaceGrant } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

export function EditGrantsDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const { data: workspaces = [] } = useWorkspaces();
  const setGrantsMutation = useSetUserApiKeyGrants();

  const [grants, setGrants] = useState<WorkspaceGrant[]>([]);

  // Pré-remplit les grants quand une clé est sélectionnée.
  useEffect(() => {
    if (apiKey) {
      setGrants(
        apiKey.workspaces.map((g) => ({
          workspace_id: g.workspace_id,
          can_read: g.can_read,
          can_write: g.can_write,
        })),
      );
    }
  }, [apiKey]);

  async function handleSave() {
    if (!apiKey) return;
    try {
      await setGrantsMutation.mutateAsync({ keyId: apiKey.id, workspaces: grants });
      toast({ title: t("grants.saved_toast") });
      onOpenChange(false);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={apiKey !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("grants.edit_title", { name: apiKey?.name ?? "" })}</DialogTitle>
          <DialogDescription>{t("grants.help")}</DialogDescription>
        </DialogHeader>
        <GrantsEditor workspaces={workspaces} value={grants} onChange={setGrants} />
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={setGrantsMutation.isPending}
          >
            {t("grants.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
