import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useOidcConfig, useUpsertOidcConfig } from "@/hooks/useOidcConfig";
import { useToast } from "@/hooks/useToast";

const schema = z.object({
  issuer: z.string().url("invalid_url"),
  client_id: z.string().min(1, "required").max(255, "too_long"),
  client_secret_ref: z
    .string()
    .min(1, "required")
    .max(255, "too_long")
    .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only"),
});

type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = { issuer: "", client_id: "", client_secret_ref: "" };

export function OidcConfigPage() {
  const { t } = useTranslation("oidc");
  const { toast } = useToast();
  const { data, isLoading } = useOidcConfig();
  const upsert = useUpsertOidcConfig();

  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: EMPTY,
  });

  // Synchronise le form quand les données serveur arrivent / changent.
  useEffect(() => {
    if (isLoading) return;
    form.reset(data ?? EMPTY);
  }, [data, isLoading, form]);

  const onSubmit = (values: FormValues) => {
    upsert.mutate(values, {
      onSuccess: (saved) => {
        toast({ title: t("save.success") });
        form.reset(saved);
      },
      onError: () => toast({ title: t("save.error"), variant: "destructive" }),
    });
  };

  const handleCancel = () => {
    form.reset(data ?? EMPTY);
  };

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="mt-6 space-y-4 rounded-md border bg-white p-6"
      >
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("fields.issuer")}
          </label>
          <Input
            {...form.register("issuer")}
            placeholder="https://keycloak.example.com/realms/yoops"
            className="mt-1"
          />
          {form.formState.errors.issuer && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.issuer.message}`)}
            </p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("fields.client_id")}
          </label>
          <Input
            {...form.register("client_id")}
            placeholder="rag"
            className="mt-1"
          />
          {form.formState.errors.client_id && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.client_id.message}`)}
            </p>
          )}
        </div>

        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("fields.client_secret_ref")}
          </label>
          <Input
            {...form.register("client_secret_ref")}
            placeholder="keycloak_rag_client_secret"
            className="mt-1 font-mono"
          />
          {form.formState.errors.client_secret_ref && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.client_secret_ref.message}`)}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={handleCancel}
            disabled={!form.formState.isDirty}
          >
            {t("actions.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={!form.formState.isDirty || upsert.isPending}
          >
            {t("actions.save")}
          </Button>
        </div>
      </form>

      <div className="mt-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-amber-900">{t("warning.sessions")}</p>
      </div>
    </div>
  );
}
