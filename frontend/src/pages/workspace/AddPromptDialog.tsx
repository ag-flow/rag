import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useCreatePrompt } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddPromptDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("prompts");
  const { toast } = useToast();
  const mutation = useCreatePrompt();

  const [name, setName] = useState("");
  const [language, setLanguage] = useState("");
  const [metadataKey, setMetadataKey] = useState("");
  const [resultType, setResultType] = useState<"text" | "json">("text");
  const [prompt, setPrompt] = useState("");
  const [description, setDescription] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setLanguage(""); setMetadataKey("");
      setResultType("text"); setPrompt(""); setDescription("");
    }
  }

  const canSubmit =
    name.trim().length > 0 &&
    language.trim().length > 0 &&
    metadataKey.trim().length > 0 &&
    prompt.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({
        name: name.trim(),
        language: language.trim(),
        metadata_key: metadataKey.trim(),
        result_type: resultType,
        prompt: prompt.trim(),
        description: description.trim() || null,
      });
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
      <DialogContent className="sm:max-w-[560px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="generate-doc-csharp"
                className="mt-1 font-mono"
              />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_language")}
              </Label>
              <Input
                value={language}
                onChange={(e) => setLanguage(e.target.value)}
                placeholder={t("field_language_placeholder")}
                className="mt-1"
              />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_metadata_key")}
              </Label>
              <Input
                value={metadataKey}
                onChange={(e) => setMetadataKey(e.target.value)}
                placeholder={t("field_metadata_key_placeholder")}
                className="mt-1 font-mono"
              />
            </div>
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_result_type")}
              </Label>
              <div className="flex gap-4 mt-2">
                {(["text", "json"] as const).map((rt) => (
                  <label key={rt} className="flex items-center gap-2 text-sm cursor-pointer">
                    <input
                      type="radio"
                      value={rt}
                      checked={resultType === rt}
                      onChange={() => setResultType(rt)}
                    />
                    {t(`field_result_type_${rt}`)}
                  </label>
                ))}
              </div>
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_prompt")}
            </Label>
            <Textarea
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              placeholder="Tu es un expert. Génère la documentation de :\n\n{content}"
              className="mt-1 font-mono text-xs min-h-[120px]"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("field_description")}
            </Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="Génère la documentation technique"
              className="mt-1"
            />
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
