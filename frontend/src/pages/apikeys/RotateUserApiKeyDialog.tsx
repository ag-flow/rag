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
import { useRotateUserApiKey } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { ShowOncePanel } from "./ShowOncePanel";
import type { UserApiKey } from "@/lib/user-api-keys.types";

interface Props {
  apiKey: UserApiKey | null;
  onOpenChange: (open: boolean) => void;
}

export function RotateUserApiKeyDialog({ apiKey, onOpenChange }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const rotateMutation = useRotateUserApiKey();
  const [newKey, setNewKey] = useState<string | null>(null);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setNewKey(null);
  }

  async function handleRotate() {
    if (!apiKey) return;
    try {
      const rotated = await rotateMutation.mutateAsync(apiKey.id);
      setNewKey(rotated.new_api_key);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={apiKey !== null} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("rotate_dialog_title")}</DialogTitle>
          <DialogDescription>{t("rotate_confirm")}</DialogDescription>
        </DialogHeader>

        {newKey === null ? (
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button
              type="button"
              onClick={() => void handleRotate()}
              disabled={rotateMutation.isPending}
            >
              {t("rotate_save")}
            </Button>
          </DialogFooter>
        ) : (
          <div className="space-y-4">
            <ShowOncePanel apiKey={newKey} />
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
