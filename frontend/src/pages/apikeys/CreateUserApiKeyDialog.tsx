import { useState } from "react";
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
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { useCreateUserApiKey } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { GrantsEditor } from "./GrantsEditor";
import { ShowOncePanel } from "./ShowOncePanel";
import type { WorkspaceGrant } from "@/lib/user-api-keys.types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateUserApiKeyDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const { data: workspaces = [] } = useWorkspaces();
  const createMutation = useCreateUserApiKey();

  const [name, setName] = useState("");
  const [grants, setGrants] = useState<WorkspaceGrant[]>([]);
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName("");
      setGrants([]);
      setCreatedKey(null);
    }
  }

  async function handleCreate() {
    try {
      const created = await createMutation.mutateAsync({ name, workspaces: grants });
      setCreatedKey(created.api_key);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("create_dialog_title")}</DialogTitle>
          <DialogDescription>{t("create_dialog_desc")}</DialogDescription>
        </DialogHeader>

        {createdKey === null ? (
          <div className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder={t("field_name_placeholder")}
                className="mt-1"
                autoFocus
              />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("grants.title")}
              </Label>
              <p className="mb-2 mt-1 text-xs text-slate-500">{t("grants.help")}</p>
              <GrantsEditor workspaces={workspaces} value={grants} onChange={setGrants} />
            </div>
            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("cancel")}
              </Button>
              <Button
                type="button"
                onClick={() => void handleCreate()}
                disabled={!name.trim() || createMutation.isPending}
              >
                {t("create_save")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <div className="space-y-4">
            <ShowOncePanel apiKey={createdKey} />
            <DialogFooter>
              <Button type="button" onClick={() => handleClose(false)}>
                {t("close")}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}
