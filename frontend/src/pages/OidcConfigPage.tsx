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
import { useAuthMethods } from "@/hooks/useAuthMethods";
import { useToast } from "@/hooks/useToast";

const schema = z.object({
  issuer: z.string().url("invalid_url"),
  client_id: z.string().min(1, "required").max(255, "too_long"),
});

type FormValues = z.infer<typeof schema>;

const EMPTY: FormValues = { issuer: "", client_id: "" };

export function OidcConfigPage() {
  const { t } = useTranslation("oidc");
  const { toast } = useToast();
  const { data, isLoading } = useOidcConfig();
  const { data: methods } = useAuthMethods();
  const upsert = useUpsertOidcConfig();

  const localDisabled = methods?.local_auth_disabled_by_config ?? false;
  const procedureSteps = t("procedure.steps", { returnObjects: true }) as string[];

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
          <label className="text-sm font-medium text-slate-700">{t("fields.issuer")}</label>
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
          <label className="text-sm font-medium text-slate-700">{t("fields.client_id")}</label>
          <Input {...form.register("client_id")} placeholder="rag" className="mt-1" />
          {form.formState.errors.client_id && (
            <p className="mt-1 text-xs text-red-600">
              {t(`errors.${form.formState.errors.client_id.message}`)}
            </p>
          )}
        </div>

        <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-sm font-medium text-slate-700">
            {t("client_secret_env.title")}
          </p>
          <p className="mt-1 text-xs text-slate-500">{t("client_secret_env.help")}</p>
          <code className="mt-2 inline-block rounded bg-slate-200 px-2 py-1 font-mono text-xs text-slate-800">
            RAG_OIDC_CLIENT_SECRET=…
          </code>
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
          <Button type="submit" disabled={!form.formState.isDirty || upsert.isPending}>
            {t("actions.save")}
          </Button>
        </div>
      </form>

      <div className="mt-4 flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-sm text-amber-900">{t("warning.sessions")}</p>
      </div>

      <section className="mt-6 rounded-md border bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-sm font-semibold text-slate-900">{t("local_auth.title")}</h2>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              localDisabled
                ? "bg-rose-50 text-rose-700"
                : "bg-emerald-50 text-emerald-700"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${localDisabled ? "bg-rose-500" : "bg-emerald-500"}`}
              aria-hidden
            />
            {localDisabled ? t("local_auth.status_disabled") : t("local_auth.status_enabled")}
          </span>
        </div>
        <p className="mt-2 text-sm text-slate-600">
          {localDisabled ? t("local_auth.help_disabled") : t("local_auth.help_enabled")}
        </p>
        <p className="mt-2 text-xs text-slate-500">{t("local_auth.env_hint")}</p>
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-900">{t("local_auth.breakglass")}</p>
          <code className="mt-2 inline-block rounded bg-amber-100 px-2 py-1 font-mono text-xs text-amber-900">
            {localDisabled ? t("local_auth.toggle_to_enable") : t("local_auth.toggle_to_disable")}
          </code>
        </div>
      </section>

      <section className="mt-6 rounded-md border bg-white p-6">
        <h2 className="text-sm font-semibold text-slate-900">{t("procedure.title")}</h2>
        <p className="mt-1 text-sm text-slate-500">{t("procedure.intro")}</p>
        <ol className="mt-4 list-decimal space-y-2 pl-5 text-sm text-slate-700">
          {procedureSteps.map((step, i) => (
            <li key={i}>{step}</li>
          ))}
        </ol>
        <p className="mt-4 text-xs text-slate-500">{t("procedure.note")}</p>
      </section>
    </div>
  );
}
