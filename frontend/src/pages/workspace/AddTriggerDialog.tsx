import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateTrigger } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddTriggerDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const mutation = useCreateTrigger(workspaceName);
  const [extension, setExtension] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setExtension("");
  }

  const canSubmit =
    extension.trim().startsWith(".") &&
    extension.trim().length >= 2 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ extension: extension.trim().toLowerCase() });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[400px]">
        <DialogHeader>
          <DialogTitle>{t("add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_extension")}
            </Label>
            <Input
              value={extension}
              onChange={(e) => setExtension(e.target.value)}
              placeholder={t("field_extension_placeholder")}
              className="mt-1 font-mono"
            />
            <p className="mt-1 text-xs text-slate-400">{t("field_extension_help")}</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
