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
import { useCreateUserApiKey } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { ScopeSelector } from "./ScopeSelector";
import { ShowOncePanel } from "./ShowOncePanel";
import { McpClientPanel } from "./McpClientPanel";
import type { KeyScope } from "@/lib/user-api-keys.types";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function CreateUserApiKeyDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const createMutation = useCreateUserApiKey();

  const [name, setName] = useState("");
  const [scope, setScope] = useState<KeyScope>("read");
  const [createdKey, setCreatedKey] = useState<string | null>(null);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName("");
      setScope("read");
      setCreatedKey(null);
    }
  }

  async function handleCreate() {
    try {
      const created = await createMutation.mutateAsync({ name, scope });
      setCreatedKey(created.api_key);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[520px]">
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
                {t("scope.title")}
              </Label>
              <p className="mb-2 mt-1 text-xs text-slate-500">{t("scope.help")}</p>
              <ScopeSelector value={scope} onChange={setScope} />
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
            <McpClientPanel apiKey={createdKey} />
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
