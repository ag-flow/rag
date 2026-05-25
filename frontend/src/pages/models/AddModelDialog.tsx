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
    dimension: z.coerce.number().int().positive("dimension_positive"),
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
      dimension: 1,
    },
  });

  useEffect(() => {
    if (!open) form.reset();
  }, [open, form]);

  const providerSelect = form.watch("providerSelect");

  const onSubmit = (v: FormValues) => {
    const provider =
      v.providerSelect === "autre" ? (v.providerOther ?? "").trim() : v.providerSelect;
    create.mutate(
      { provider, model: v.model, dimension: v.dimension },
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
