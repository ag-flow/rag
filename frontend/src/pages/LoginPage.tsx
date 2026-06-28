import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useAuthMethods } from "@/hooks/useAuthMethods";

const loginSchema = z.object({
  username: z.string().min(1, "required"),
  password: z.string().min(1, "required"),
});

const setupSchema = z
  .object({
    username: z.string().min(1, "required"),
    email: z.string().email("invalid email"),
    password: z.string().min(8, "min 8 chars"),
    confirm_password: z.string().min(1, "required"),
  })
  .refine((d) => d.password === d.confirm_password, {
    path: ["confirm_password"],
    message: "passwords_mismatch",
  });

type LoginValues = z.infer<typeof loginSchema>;
type SetupValues = z.infer<typeof setupSchema>;

function getNextFromSearch(): string {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next");
  if (next && next.startsWith("/") && !next.startsWith("//") && !next.startsWith("\\")) {
    return next;
  }
  return "/workspaces";
}

function SetupForm() {
  const { t } = useTranslation("login");
  const [error, setError] = useState<string | null>(null);
  const form = useForm<SetupValues>({
    resolver: zodResolver(setupSchema),
    defaultValues: { username: "admin", email: "", password: "", confirm_password: "" },
  });

  const onSubmit = async (values: SetupValues) => {
    setError(null);
    const resp = await fetch("/api/setup/init-admin", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: values.username,
        email: values.email,
        password: values.password,
      }),
    });
    if (resp.ok) {
      window.location.href = "/ui" + getNextFromSearch();
      return;
    }
    if (resp.status === 409) {
      window.location.reload();
    } else {
      setError(t("setup.errors.generic", { status: resp.status }));
    }
  };

  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-md border bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900 mb-1">{t("setup.title")}</h1>
        <p className="text-sm text-slate-500 mb-5">{t("setup.subtitle")}</p>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div>
            <label htmlFor="setup-username" className="text-sm font-medium text-slate-700">
              {t("setup.fields.username")}
            </label>
            <Input id="setup-username" {...form.register("username")} className="mt-1" />
            {form.formState.errors.username && (
              <p className="text-xs text-red-600 mt-1">{form.formState.errors.username.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="setup-email" className="text-sm font-medium text-slate-700">
              {t("setup.fields.email")}
            </label>
            <Input id="setup-email" type="email" {...form.register("email")} className="mt-1" />
            {form.formState.errors.email && (
              <p className="text-xs text-red-600 mt-1">{form.formState.errors.email.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="setup-password" className="text-sm font-medium text-slate-700">
              {t("setup.fields.password")}
            </label>
            <Input
              id="setup-password"
              type="password"
              {...form.register("password")}
              className="mt-1"
            />
            {form.formState.errors.password && (
              <p className="text-xs text-red-600 mt-1">{form.formState.errors.password.message}</p>
            )}
          </div>
          <div>
            <label htmlFor="setup-confirm" className="text-sm font-medium text-slate-700">
              {t("setup.fields.confirm_password")}
            </label>
            <Input
              id="setup-confirm"
              type="password"
              {...form.register("confirm_password")}
              className="mt-1"
            />
            {form.formState.errors.confirm_password && (
              <p className="text-xs text-red-600 mt-1">
                {form.formState.errors.confirm_password.message === "passwords_mismatch"
                  ? t("setup.errors.passwords_mismatch")
                  : form.formState.errors.confirm_password.message}
              </p>
            )}
          </div>
          {error && <p className="text-sm text-red-600">{error}</p>}
          <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
            {t("setup.submit")}
          </Button>
        </form>
      </div>
    </div>
  );
}

export function LoginPage() {
  const { t } = useTranslation("login");
  const { data: methods, isLoading } = useAuthMethods();
  const [error, setError] = useState<string | null>(null);
  const form = useForm<LoginValues>({
    resolver: zodResolver(loginSchema),
    defaultValues: { username: "", password: "" },
  });

  const onSubmit = async (values: LoginValues) => {
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
    } else {
      setError(t("errors.generic", { status: resp.status }));
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

  if (methods?.needs_setup) {
    return <SetupForm />;
  }

  const showOidc = !!methods?.oidc_configured;
  const showLocal = !!methods?.local_auth_enabled;

  return (
    <div className="flex h-screen items-center justify-center bg-slate-50">
      <div className="w-full max-w-md rounded-md border bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold text-slate-900 mb-4">{t("title")}</h1>

        {!showOidc && !showLocal && (
          <p className="text-sm text-red-600">{t("errors.no_method")}</p>
        )}

        {showOidc && (
          <Button type="button" onClick={handleSsoClick} className="w-full mb-4">
            {t("oidc.button")}
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
