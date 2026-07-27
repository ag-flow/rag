import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useOidcConfig, useUpsertOidcConfig } from "@/hooks/useOidcConfig";
import {
  useClientSecretStatus,
  useLocalLogin,
  usePublicUrl,
  useSetClientSecret,
  useSetLocalLogin,
  useSetPublicUrl,
} from "@/hooks/useAdminAuthConfig";
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
  const upsert = useUpsertOidcConfig();

  const { data: secretStatus } = useClientSecretStatus();
  const setSecret = useSetClientSecret();
  const [secretInput, setSecretInput] = useState("");

  const { data: localLogin } = useLocalLogin();
  const setLocalLogin = useSetLocalLogin();
  const localEnabled = localLogin?.enabled ?? true;

  const { data: publicUrl } = usePublicUrl();
  const setPublicUrl = useSetPublicUrl();
  const [publicUrlInput, setPublicUrlInput] = useState("");
  useEffect(() => {
    setPublicUrlInput(publicUrl?.value ?? "");
  }, [publicUrl]);

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

  const handleSaveSecret = () => {
    if (!secretInput) return;
    setSecret.mutate(secretInput, {
      onSuccess: () => {
        toast({ title: t("client_secret.saved") });
        setSecretInput("");
      },
      onError: () => toast({ title: t("client_secret.error"), variant: "destructive" }),
    });
  };

  const handleSavePublicUrl = () => {
    setPublicUrl.mutate(publicUrlInput.trim(), {
      onSuccess: () => toast({ title: t("public_url.saved") }),
      onError: () => toast({ title: t("public_url.error"), variant: "destructive" }),
    });
  };

  const handleToggleLocal = (enabled: boolean) => {
    setLocalLogin.mutate(enabled, {
      onError: () => toast({ title: t("local_auth.error"), variant: "destructive" }),
    });
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
          <h2 className="text-sm font-semibold text-slate-900">{t("client_secret.title")}</h2>
          <span
            className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-medium ${
              secretStatus?.configured
                ? "bg-emerald-50 text-emerald-700"
                : "bg-slate-100 text-slate-500"
            }`}
          >
            <span
              className={`h-2 w-2 rounded-full ${
                secretStatus?.configured ? "bg-emerald-500" : "bg-slate-400"
              }`}
              aria-hidden
            />
            {secretStatus?.configured ? t("client_secret.set") : t("client_secret.unset")}
          </span>
        </div>
        <p className="mt-2 text-xs text-slate-500">{t("client_secret.help")}</p>
        <div className="mt-3 flex items-center gap-2">
          <Input
            type="password"
            value={secretInput}
            onChange={(e) => setSecretInput(e.target.value)}
            placeholder={t("client_secret.placeholder")}
            className="flex-1 font-mono"
            autoComplete="off"
          />
          <Button
            type="button"
            onClick={handleSaveSecret}
            disabled={!secretInput || setSecret.isPending}
          >
            {t("client_secret.submit")}
          </Button>
        </div>
      </section>

      <section className="mt-6 rounded-md border bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <h2 className="text-sm font-semibold text-slate-900">{t("public_url.title")}</h2>
          {!publicUrl?.value && (
            <span className="inline-flex items-center rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium text-slate-500">
              {t("public_url.derived")}
            </span>
          )}
        </div>
        <p className="mt-2 text-xs text-slate-500">{t("public_url.help")}</p>
        <div className="mt-3 flex items-center gap-2">
          <Input
            value={publicUrlInput}
            onChange={(e) => setPublicUrlInput(e.target.value)}
            placeholder={t("public_url.placeholder")}
            className="flex-1 font-mono"
            aria-label={t("public_url.title")}
          />
          <Button
            type="button"
            onClick={handleSavePublicUrl}
            disabled={setPublicUrl.isPending || publicUrlInput.trim() === (publicUrl?.value ?? "")}
          >
            {t("public_url.submit")}
          </Button>
        </div>
      </section>

      <section className="mt-6 rounded-md border bg-white p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <h2 className="text-sm font-semibold text-slate-900">{t("local_auth.title")}</h2>
            <p className="mt-1 text-sm text-slate-600">
              {localEnabled ? t("local_auth.help_enabled") : t("local_auth.help_disabled")}
            </p>
          </div>
          <Switch
            checked={localEnabled}
            onCheckedChange={handleToggleLocal}
            disabled={setLocalLogin.isPending}
            aria-label={t("local_auth.title")}
          />
        </div>
        <div className="mt-3 rounded-md border border-amber-200 bg-amber-50 px-4 py-3">
          <p className="text-sm text-amber-900">{t("local_auth.breakglass")}</p>
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
