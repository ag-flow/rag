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
import { cn } from "@/lib/utils";

const COMMON_EXTENSIONS: { ext: string; label: string }[] = [
  { ext: ".cs",   label: "C#" },
  { ext: ".py",   label: "Python" },
  { ext: ".ts",   label: "TypeScript" },
  { ext: ".tsx",  label: "TSX" },
  { ext: ".js",   label: "JavaScript" },
  { ext: ".jsx",  label: "JSX" },
  { ext: ".java", label: "Java" },
  { ext: ".go",   label: "Go" },
  { ext: ".rs",   label: "Rust" },
  { ext: ".md",   label: "Markdown" },
  { ext: ".json", label: "JSON" },
  { ext: ".yaml", label: "YAML" },
  { ext: ".yml",  label: "YAML" },
  { ext: ".sql",  label: "SQL" },
  { ext: ".sh",   label: "Shell" },
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
  const [extension, setExtension] = useState("");
  const [custom, setCustom] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) { setExtension(""); setCustom(""); }
  }

  // La valeur finale : badge cliqué OU champ custom
  const finalExt = extension || custom.trim();
  const canSubmit =
    finalExt.startsWith(".") &&
    finalExt.length >= 2 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ extension: finalExt.toLowerCase() });
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
              {t("field_extension")}
            </Label>
            <div className="flex flex-wrap gap-1.5">
              {COMMON_EXTENSIONS.map(({ ext, label }) => (
                <button
                  key={ext}
                  type="button"
                  onClick={() => { setExtension(ext); setCustom(""); }}
                  className={cn(
                    "rounded border px-2.5 py-1 text-xs font-mono transition-colors",
                    extension === ext
                      ? "border-sky-500 bg-sky-50 text-sky-700 font-semibold"
                      : "border-slate-200 bg-white text-slate-600 hover:border-slate-300 hover:bg-slate-50",
                  )}
                >
                  {ext}
                  <span className="ml-1 text-slate-400 font-sans">{label}</span>
                </button>
              ))}
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_extension_other")}
            </Label>
            <Input
              value={custom}
              onChange={(e) => { setCustom(e.target.value); setExtension(""); }}
              placeholder={t("field_extension_placeholder")}
              className="mt-1 font-mono"
            />
          </div>

          {finalExt && (
            <p className="text-xs text-slate-500">
              {t("field_extension_selected")} <span className="font-mono font-semibold text-slate-700">{finalExt}</span>
            </p>
          )}

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
