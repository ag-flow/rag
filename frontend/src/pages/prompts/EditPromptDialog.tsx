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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { usePatchPrompt } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import type { PromptTemplate, PromptTemplatePatch } from "@/lib/enrichments.types";

interface Props {
  prompt: PromptTemplate | null;
  onOpenChange: (open: boolean) => void;
}

/** Édition d'un prompt utilisateur : description, corps du prompt et, pour un
 *  result_type=json, le schéma attendu. Les prompts système sont immuables
 *  (le bouton d'édition est désactivé en amont). */
export function EditPromptDialog({ prompt, onOpenChange }: Props) {
  const { t } = useTranslation("prompts");
  const { toast } = useToast();
  const patchMutation = usePatchPrompt();

  const [description, setDescription] = useState("");
  const [body, setBody] = useState("");
  const [schema, setSchema] = useState("");
  const [schemaError, setSchemaError] = useState(false);

  useEffect(() => {
    if (prompt) {
      setDescription(prompt.description ?? "");
      setBody(prompt.prompt);
      setSchema(prompt.result_schema ? JSON.stringify(prompt.result_schema, null, 2) : "");
      setSchemaError(false);
    }
  }, [prompt]);

  async function handleSave() {
    if (!prompt) return;
    const payload: PromptTemplatePatch = {
      description: description || null,
      prompt: body,
    };
    if (prompt.result_type === "json") {
      if (schema.trim()) {
        try {
          payload.result_schema = JSON.parse(schema) as object;
        } catch {
          setSchemaError(true);
          return;
        }
      } else {
        payload.result_schema = null;
      }
    }
    try {
      await patchMutation.mutateAsync({ id: prompt.id, payload });
      toast({ title: t("edit.saved") });
      onOpenChange(false);
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={prompt !== null} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[90vh] overflow-y-auto sm:max-w-[640px]">
        <DialogHeader>
          <DialogTitle>{t("edit.title")}</DialogTitle>
          <DialogDescription className="font-mono text-xs">
            {prompt?.name} · {prompt?.language} · {prompt?.metadata_key}
          </DialogDescription>
        </DialogHeader>

        <div className="min-w-0 space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("edit.description_label")}
            </Label>
            <Input
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("edit.prompt_label")}
            </Label>
            <Textarea
              value={body}
              onChange={(e) => setBody(e.target.value)}
              rows={10}
              className="mt-1 font-mono text-xs"
            />
          </div>

          {prompt?.result_type === "json" && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("edit.schema_label")}
              </Label>
              <Textarea
                value={schema}
                onChange={(e) => {
                  setSchema(e.target.value);
                  setSchemaError(false);
                }}
                rows={6}
                className="mt-1 font-mono text-xs"
              />
              {schemaError && (
                <p className="mt-1 text-xs text-rose-600">{t("edit.schema_invalid")}</p>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("cancel")}
            </Button>
            <Button
              type="button"
              onClick={() => void handleSave()}
              disabled={!body.trim() || patchMutation.isPending}
            >
              {t("edit.save")}
            </Button>
          </DialogFooter>
        </div>
      </DialogContent>
    </Dialog>
  );
}
