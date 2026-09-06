import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import type { AuthMethods } from "@/hooks/useAuthMethods";
import { AuthCard } from "@/pages/login/AuthCard";

const loginSchema = z.object({
  username: z.string().min(1, "required"),
  password: z.string().min(1, "required"),
});

type LoginValues = z.infer<typeof loginSchema>;

interface LoginCardProps {
  methods: AuthMethods;
  nextPath: string;
  onSetup: () => void;
}

/** Carte de connexion : LOCAL en premier (bouton primaire), OIDC en action
 * secondaire — décision de la fiche 2ca3ceb8. */
export function LoginCard({ methods, nextPath, onSetup }: LoginCardProps) {
  const { t } = useTranslation("login");
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const showOidc = methods.oidc_configured;
  const showLocal = methods.local_auth_enabled;

  const onSubmit = async (values: LoginValues) => {
    setError(null);
    const resp = await fetch("/auth/local/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
    if (resp.ok) {
      window.location.href = "/ui" + nextPath;
      return;
    }
    setError(
      resp.status === 401
        ? t("errors.invalid_credentials")
        : t("errors.generic", { status: resp.status }),
    );
  };

  const handleSsoClick = () => {
    const next = encodeURIComponent("/ui" + nextPath);
    window.location.href = `/auth/login?next=${next}`;
  };

  const fieldError = (name: keyof LoginValues): string | undefined =>
    form.formState.errors[name] ? t("errors.required") : undefined;

  return (
    <AuthCard>
      <h2 className="font-display text-xl font-semibold text-slate-900">{t("title")}</h2>

      {!showOidc && !showLocal && (
        <p role="alert" className="mt-3 text-sm text-rose-600">
          {t("errors.no_method")}
        </p>
      )}

      {showLocal && (
        <form onSubmit={form.handleSubmit(onSubmit)} className="mt-4 space-y-3" noValidate>
          {!showOidc && (
            <p className="rounded-sm border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-800">
              {t("info.oidc_not_configured")}
            </p>
          )}
          <div>
            <label htmlFor="username" className="text-sm font-medium text-slate-700">
              {t("local.fields.username")}
            </label>
            <Input
              id="username"
              autoComplete="username"
              {...form.register("username", { onChange: () => setError(null) })}
              className="mt-1"
            />
            {fieldError("username") && (
              <p className="mt-1 text-xs text-rose-600">{fieldError("username")}</p>
            )}
          </div>
          <div>
            <label htmlFor="password" className="text-sm font-medium text-slate-700">
              {t("local.fields.password")}
            </label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              {...form.register("password", { onChange: () => setError(null) })}
              className="mt-1"
            />
            {fieldError("password") && (
              <p className="mt-1 text-xs text-rose-600">{fieldError("password")}</p>
            )}
          </div>
          {error && (
            <p
              role="alert"
              className="rounded-sm border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
            >
              {error}
            </p>
          )}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {t("local.submit")}
          </Button>
        </form>
      )}

      {showOidc && showLocal && (
        <div className="my-4 flex items-center gap-2 text-xs text-slate-400">
          <div className="flex-1 border-t" />
          <span>{t("info.separator_or")}</span>
          <div className="flex-1 border-t" />
        </div>
      )}

      {showOidc && (
        <Button
          type="button"
          variant={showLocal ? "outline" : "default"}
          onClick={handleSsoClick}
          className="w-full"
        >
          {t("oidc.button")}
        </Button>
      )}

      {methods.needs_setup && (
        <button
          type="button"
          onClick={onSetup}
          className="mt-4 text-sm text-accent-700 hover:text-accent-800 hover:underline"
        >
          {t("setup_link")}
        </button>
      )}
    </AuthCard>
  );
}
