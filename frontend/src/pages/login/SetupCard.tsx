import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { AuthCard } from "@/pages/login/AuthCard";

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

type SetupValues = z.infer<typeof setupSchema>;

interface SetupCardProps {
  nextPath: string;
  onBack: () => void;
}

/** Variante « premier démarrage » : création du compte administrateur local.
 * N'est atteignable que si aucun utilisateur n'existe (needs_setup). */
export function SetupCard({ nextPath, onBack }: SetupCardProps) {
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
      window.location.href = "/ui" + nextPath;
      return;
    }
    if (resp.status === 409) {
      window.location.reload();
    } else {
      setError(t("setup.errors.generic", { status: resp.status }));
    }
  };

  const fieldError = (name: keyof SetupValues): string | undefined => {
    const message = form.formState.errors[name]?.message;
    if (!message) return undefined;
    return message === "passwords_mismatch" ? t("setup.errors.passwords_mismatch") : message;
  };

  return (
    <AuthCard>
      <h2 className="font-display text-xl font-semibold text-slate-900">{t("setup.title")}</h2>
      <p className="mb-5 mt-1 text-sm text-slate-500">{t("setup.subtitle")}</p>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3" noValidate>
        {(
          [
            ["username", "text"],
            ["email", "email"],
            ["password", "password"],
            ["confirm_password", "password"],
          ] as const
        ).map(([name, type]) => (
          <div key={name}>
            <label htmlFor={`setup-${name}`} className="text-sm font-medium text-slate-700">
              {t(`setup.fields.${name}`)}
            </label>
            <Input
              id={`setup-${name}`}
              type={type}
              {...form.register(name, { onChange: () => setError(null) })}
              className="mt-1"
            />
            {fieldError(name) && <p className="mt-1 text-xs text-rose-600">{fieldError(name)}</p>}
          </div>
        ))}
        {error && (
          <p
            role="alert"
            className="rounded-sm border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700"
          >
            {error}
          </p>
        )}
        <Button type="submit" className="w-full" disabled={form.formState.isSubmitting}>
          {t("setup.submit")}
        </Button>
      </form>
      <button
        type="button"
        onClick={onBack}
        className="mt-4 text-sm text-accent-700 hover:text-accent-800 hover:underline"
      >
        {t("setup.back")}
      </button>
    </AuthCard>
  );
}
