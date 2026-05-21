import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useAuthMethods } from "@/hooks/useAuthMethods";

const schema = z.object({
  username: z.string().min(1, "required"),
  password: z.string().min(1, "required"),
});

type FormValues = z.infer<typeof schema>;

function getNextFromSearch(): string {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  return next && next.startsWith("/") && !next.startsWith("//") ? next : "/workspaces";
}

export function LoginPage() {
  const { t } = useTranslation("login");
  const { data: methods, isLoading } = useAuthMethods();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { username: "admin", password: "" },
  });

  const onSubmit = async (values: FormValues) => {
    setError(null);
    const resp = await fetch("/auth/local/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (resp.ok) {
      window.location.href = "/ui" + getNextFromSearch();
      return;
    }
    if (resp.status === 401) {
      setError(t("errors.invalid_credentials"));
    } else if (resp.status === 503) {
      setError(t("errors.bootstrap_disabled"));
    } else {
      setError(`Erreur ${resp.status}`);
    }
  };

  const handleSsoClick = () => {
    const next = encodeURIComponent("/ui" + getNextFromSearch());
    window.location.href = `/auth/login?next=${next}`;
  };

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center bg-slate-50">
        <LoadingSpinner />
      </div>
    );
  }

  const showOidc = !!methods?.oidc_configured;
  const showLocal = !!methods?.bootstrap_enabled;

  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-md border bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900 mb-4">{t("title")}</h1>

        {!showOidc && !showLocal && (
          <p className="text-sm text-red-600">{t("errors.no_method")}</p>
        )}

        {showOidc && (
          <Button type="button" onClick={handleSsoClick} className="w-full mb-4">
            → {t("oidc.button")}
          </Button>
        )}

        {showOidc && showLocal && (
          <div className="my-4 flex items-center gap-2 text-xs text-slate-400">
            <div className="flex-1 border-t" />
            <span>{t("info.separator_or")}</span>
            <div className="flex-1 border-t" />
          </div>
        )}

        {showLocal && (
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
            {!showOidc && (
              <p className="text-sm text-amber-800 bg-amber-50 border border-amber-200 rounded px-3 py-2">
                {t("info.oidc_not_configured")}
              </p>
            )}
            <div>
              <label htmlFor="username" className="text-sm font-medium text-slate-700">
                {t("local.fields.username")}
              </label>
              <Input id="username" {...form.register("username")} className="mt-1" />
            </div>
            <div>
              <label htmlFor="password" className="text-sm font-medium text-slate-700">
                {t("local.fields.password")}
              </label>
              <Input
                id="password"
                type="password"
                {...form.register("password")}
                className="mt-1"
              />
            </div>
            {error && <p className="text-sm text-red-600">{error}</p>}
            <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
              {t("local.submit")}
            </Button>
          </form>
        )}
      </div>
    </div>
  );
}
