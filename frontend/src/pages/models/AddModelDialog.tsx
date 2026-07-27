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
import { ApiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import { useCreateModel } from "@/hooks/useModels";

const PROVIDERS = ["openai", "voyage", "ollama", "autre"] as const;

const schema = z
  .object({
    providerSelect: z.enum(PROVIDERS),
    providerOther: z.string().optional(),
    model: z.string().min(1, "model_required"),
    kind: z.enum(["embedding", "llm", "rerank"]),
    dimension: z.coerce.number().int().positive("dimension_positive"),
    urlTemplate: z.string().optional(),
  })
  .refine(
    (v) => v.providerSelect !== "autre" || (v.providerOther && v.providerOther.trim().length > 0),
    { message: "provider_other_required", path: ["providerOther"] },
  );

type FormValues = z.infer<typeof schema>;

interface Props {
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

export function AddModelDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("models");
  const { toast } = useToast();
  const create = useCreateModel();
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      providerSelect: "openai",
      providerOther: "",
      model: "",
      kind: "embedding",
      dimension: 1,
      urlTemplate: "",
    },
  });

  useEffect(() => {
    if (!open) form.reset();
  }, [open, form]);

  const providerSelect = form.watch("providerSelect");
  const kind = form.watch("kind");

  const onSubmit = (v: FormValues) => {
    const provider =
      v.providerSelect === "autre" ? (v.providerOther ?? "").trim() : v.providerSelect;
    create.mutate(
      {
        provider,
        model: v.model,
        kind: v.kind,
        // Seul un modèle d'embedding a une dimension.
        dimension: v.kind === "embedding" ? v.dimension : null,
        url_template: (v.urlTemplate ?? "").trim() || null,
      },
      {
        onSuccess: () => {
          toast({ title: t("dialog.add.success") });
          onOpenChange(false);
        },
        onError: (err) => {
          if (err instanceof ApiError && err.status === 409) {
            toast({ title: t("errors.duplicate"), variant: "destructive" });
          } else {
            toast({ title: t("dialog.add.error"), variant: "destructive" });
          }
        },
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("dialog.add.title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-700">{t("dialog.add.provider")}</label>
            <Select
              value={providerSelect}
              onValueChange={(v) =>
                form.setValue("providerSelect", v as (typeof PROVIDERS)[number])
              }
            >
              <SelectTrigger>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p === "autre" ? t("dialog.add.providerOther") : p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {providerSelect === "autre" && (
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("dialog.add.providerOtherLabel")}
              </label>
              <Input {...form.register("providerOther")} placeholder="mistral" />
              {form.formState.errors.providerOther && (
                <p className="text-xs text-red-600 mt-1">
                  {t(`dialog.add.errors.${form.formState.errors.providerOther.message}`)}
                </p>
              )}
            </div>
          )}
          <div>
            <label className="text-xs font-medium text-slate-700">{t("dialog.add.model")}</label>
            <Input {...form.register("model")} placeholder="text-embedding-3-small" />
            {form.formState.errors.model && (
              <p className="text-xs text-red-600 mt-1">
                {t(`dialog.add.errors.${form.formState.errors.model.message}`)}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">{t("dialog.add.kind")}</label>
            <Select
              value={kind}
              onValueChange={(v) => form.setValue("kind", v as "embedding" | "llm" | "rerank")}
            >
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
              {form.formState.errors.dimension && (
                <p className="text-xs text-red-600 mt-1">
                  {t(`dialog.add.errors.${form.formState.errors.dimension.message}`)}
                </p>
              )}
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
            <Button type="submit" disabled={create.isPending}>
              {t("dialog.add.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
