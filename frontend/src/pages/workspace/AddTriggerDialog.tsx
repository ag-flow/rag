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
import { useCreateTrigger } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

// Raccourcis : un clic préremplit le champ avec le pattern « toute
// profondeur » de l'extension ; le pattern reste librement éditable.
const COMMON_PATTERNS: { pattern: string; label: string }[] = [
  { pattern: "**/*.cs", label: "C#" },
  { pattern: "**/*.py", label: "Python" },
  { pattern: "**/*.ts", label: "TypeScript" },
  { pattern: "**/*.tsx", label: "TSX" },
  { pattern: "**/*.js", label: "JavaScript" },
  { pattern: "**/*.java", label: "Java" },
  { pattern: "**/*.go", label: "Go" },
  { pattern: "**/*.rs", label: "Rust" },
  { pattern: "**/*.md", label: "Markdown" },
  { pattern: "**/*.json", label: "JSON" },
  { pattern: "**/*.yaml", label: "YAML" },
  { pattern: "**/*.sql", label: "SQL" },
  { pattern: "**/*.sh", label: "Shell" },
];

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddTriggerDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("triggers");
  const { toast } = useToast();
  const mutation = useCreateTrigger(workspaceName);
  const [pattern, setPattern] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) setPattern("");
  }

  const finalPattern = pattern.trim();
  const canSubmit =
    finalPattern.length > 0 && !finalPattern.startsWith("/") && !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ pattern: finalPattern });
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
      <DialogContent className="sm:max-w-[460px]">
        <DialogHeader>
          <DialogTitle>{t("add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600 mb-2 block">
              {t("field_pattern_presets")}
            </Label>
            <div className="flex flex-wrap gap-1.5">
              {COMMON_PATTERNS.map(({ pattern: preset, label }) => (
                <button
                  key={preset}
                  type="button"
                  onClick={() => setPattern(preset)}
                  className={cn(
                    "rounded border px-2.5 py-1 text-xs font-mono transition-colors",
                    pattern === preset
                      ? "border-sky-500 bg-sky-50 text-sky-700 font-semibold"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50",
                  )}
                >
                  {preset}
                  <span className="ml-1 text-slate-400 font-sans">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_pattern")}
            </Label>
            <Input
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder={t("field_pattern_placeholder")}
              className="mt-1 font-mono"
            />
            <p className="mt-1 text-xs text-slate-400">{t("field_pattern_help")}</p>
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
