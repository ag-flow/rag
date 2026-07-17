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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreatePrompt, useLanguages } from "@/hooks/useEnrichments";
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
  const { data: languages = [] } = useLanguages();

  const [name, setName] = useState("");
  const [language, setLanguage] = useState("");
  const [metadataKey, setMetadataKey] = useState("");
  const [resultType, setResultType] = useState<"text" | "json">("text");
  const [prompt, setPrompt] = useState("");
  const [description, setDescription] = useState("");
  const [mode, setMode] = useState<"document" | "chunk" | "region">("document");
  const [regionType, setRegionType] = useState("code_fence");
  const [regionQualifier, setRegionQualifier] = useState("");

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName("");
      setLanguage("");
      setMetadataKey("");
      setResultType("text");
      setPrompt("");
      setDescription("");
      setMode("document");
      setRegionType("code_fence");
      setRegionQualifier("");
    }
  }

  // Axes contextual retrieval (spec « Prompt B ») : le mode dérive le couple
  // (target, timing) — seules les combinaisons supportées sont proposables.
  function buildAxes(): { target: string; timing: "post_index_metadata" | "embedding_inline" } {
    if (mode === "document") return { target: "document", timing: "post_index_metadata" };
    if (mode === "chunk") return { target: "chunk", timing: "embedding_inline" };
    const qualifier = regionQualifier.trim();
    return {
      target: qualifier ? `region:${regionType}:${qualifier}` : `region:${regionType}`,
      timing: "embedding_inline",
    };
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
        ...buildAxes(),
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
              <Select value={language} onValueChange={setLanguage}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("field_language_placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  {languages.map((l) => (
                    <SelectItem key={l.code} value={l.code}>
                      {l.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
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

          <div className="grid grid-cols-2 gap-3">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("field_mode")}
              </Label>
              <Select value={mode} onValueChange={(v) => setMode(v as typeof mode)}>
                <SelectTrigger className="mt-1" aria-label={t("field_mode")}>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="document">{t("mode_document")}</SelectItem>
                  <SelectItem value="chunk">{t("mode_chunk")}</SelectItem>
                  <SelectItem value="region">{t("mode_region")}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            {mode === "region" && (
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <Label className="text-xs uppercase tracking-wider text-slate-600">
                    {t("field_region_type")}
                  </Label>
                  <Select value={regionType} onValueChange={setRegionType}>
                    <SelectTrigger className="mt-1" aria-label={t("field_region_type")}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {["prose", "code_fence", "table", "frontmatter", "html_block"].map(
                        (rt) => (
                          <SelectItem key={rt} value={rt}>
                            {rt}
                          </SelectItem>
                        ),
                      )}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs uppercase tracking-wider text-slate-600">
                    {t("field_region_qualifier")}
                  </Label>
                  <Input
                    value={regionQualifier}
                    onChange={(e) => setRegionQualifier(e.target.value)}
                    placeholder="mermaid"
                    className="mt-1 font-mono"
                  />
                </div>
              </div>
            )}
          </div>
          {mode !== "document" && (
            <p className="text-xs text-slate-500">{t("mode_inline_hint")}</p>
          )}

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
