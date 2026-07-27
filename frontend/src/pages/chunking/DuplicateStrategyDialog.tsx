import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useDuplicateStrategy } from "@/hooks/useChunkingStrategies";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { StrategyOut } from "@/lib/chunking-strategies.types";

interface Props {
  strategy: StrategyOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function DuplicateStrategyDialog({ strategy, open, onOpenChange }: Props) {
  const { t } = useTranslation("chunking_strategies");
  const { toast } = useToast();
  const duplicate = useDuplicateStrategy();
  const [label, setLabel] = useState("");

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!label.trim() || duplicate.isPending) return;
    try {
      await duplicate.mutateAsync({ id: strategy.id, label: label.trim() });
      toast({ title: t("toasts.duplicated") });
      onOpenChange(false);
    } catch (err) {
      const title =
        err instanceof ApiError && err.status === 409 ? t("errors.conflict") : t("errors.generic");
      toast({ title, variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[440px]">
        <DialogHeader>
          <DialogTitle>{t("duplicate.title", { label: strategy.label })}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500">{t("duplicate.hint")}</p>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="duplicate-label">{t("duplicate.label")}</Label>
            <Input
              id="duplicate-label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              maxLength={128}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={!label.trim() || duplicate.isPending}>
              {t("duplicate.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
