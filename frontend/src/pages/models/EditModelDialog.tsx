import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useToast } from "@/hooks/useToast";
import { useUpdateModel } from "@/hooks/useModels";
import type { ModelEntry, ModelKind } from "@/lib/models.types";

const schema = z.object({
  kind: z.enum(["embedding", "llm", "rerank"]),
  dimension: z.coerce.number().int().positive("dimension_positive"),
  urlTemplate: z.string().optional(),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  entry: ModelEntry | null;
  onOpenChange: (o: boolean) => void;
}

/** Édition d'un modèle possédé — la clé (provider, model) est immuable. */
export function EditModelDialog({ entry, onOpenChange }: Props) {
  const { t } = useTranslation("models");
  const { toast } = useToast();
  const update = useUpdateModel();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { kind: "embedding", dimension: 1, urlTemplate: "" },
  });

  useEffect(() => {
    if (entry) {
      form.reset({
        kind: entry.kind,
        dimension: entry.dimension ?? 1,
        urlTemplate: entry.url_template ?? "",
      });
    }
  }, [entry, form]);

  const kind = form.watch("kind");

  const onSubmit = (v: FormValues) => {
    if (!entry) return;
    update.mutate(
      {
        provider: entry.provider,
        model: entry.model,
        payload: {
          kind: v.kind,
          dimension: v.kind === "embedding" ? v.dimension : null,
          url_template: (v.urlTemplate ?? "").trim() || null,
        },
      },
      {
        onSuccess: () => {
          toast({ title: t("dialog.edit.success") });
          onOpenChange(false);
        },
        onError: () => toast({ title: t("dialog.edit.error"), variant: "destructive" }),
      },
    );
  };

  return (
    <Dialog open={entry !== null} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dialog.edit.title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div className="text-sm text-slate-600">
            <code className="font-mono">{entry?.provider}</code> /{" "}
            <code className="font-mono">{entry?.model}</code>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("dialog.add.kind")}</label>
            <Select value={kind} onValueChange={(v) => form.setValue("kind", v as ModelKind)}>
              <SelectTrigger aria-label={t("dialog.add.kind")}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="embedding">{t("dialog.add.kind_embedding")}</SelectItem>
                <SelectItem value="rerank">{t("dialog.add.kind_rerank")}</SelectItem>
                <SelectItem value="llm">{t("dialog.add.kind_llm")}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          {kind === "embedding" && (
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("dialog.add.dimension")}
              </label>
              <Input type="number" {...form.register("dimension")} min={1} />
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("dialog.add.url_template")}
            </label>
            <Input
              {...form.register("urlTemplate")}
              className="font-mono"
              placeholder="{url}/openai/deployments/mon-deploiement/embeddings?api-version=2024-02-01"
            />
            <p className="text-xs text-slate-400 mt-1">{t("dialog.add.url_template_hint")}</p>
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("dialog.cancel")}
            </Button>
            <Button type="submit" disabled={update.isPending}>
              {t("dialog.edit.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
