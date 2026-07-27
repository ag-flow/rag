import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useToast } from "@/hooks/useToast";
import { applyDensity, getStoredDensity, type Density } from "@/lib/density";
import { profileApi } from "@/lib/profile";

/** Profil utilisateur : email (pivot d'identité, matching OIDC) + GUID
 *  d'identité (matching OBO des appels MCP faits « en mon nom »). */
export function ProfilePage() {
  const { t } = useTranslation("profile");
  const { toast } = useToast();
  const qc = useQueryClient();

  const {
    data: profile,
    isLoading,
    isError,
  } = useQuery({
    queryKey: ["me", "profile"],
    queryFn: profileApi.get,
  });

  const [email, setEmail] = useState("");
  const [identity, setIdentity] = useState("");

  useEffect(() => {
    if (profile) {
      setEmail(profile.email);
      setIdentity(profile.identity ?? "");
    }
  }, [profile]);

  const save = useMutation({
    mutationFn: () => profileApi.update({ email, identity }),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["me", "profile"] });
      toast({ title: t("saved") });
    },
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : "";
      const key = msg.includes("identity_taken")
        ? "error_identity_taken"
        : msg.includes("email_taken")
          ? "error_email_taken"
          : msg.includes("invalid_identity")
            ? "error_invalid_identity"
            : "error_generic";
      toast({ title: t(key), variant: "destructive" });
    },
  });

  const generate = useMutation({
    mutationFn: profileApi.generateIdentity,
    onSuccess: (r) => setIdentity(r.identity),
  });

  if (isLoading) return <LoadingSpinner />;
  if (isError || !profile) {
    return <p className="p-6 text-sm text-rose-600">{t("load_error")}</p>;
  }

  const emailChanged = email !== profile.email;

  return (
    <div className="mx-auto max-w-2xl space-y-6 p-6">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("page_subtitle")}</p>
      </div>

      <section className="space-y-4 rounded-md border bg-white p-4">
        <div>
          <Label className="text-xs uppercase tracking-wider text-slate-600">
            {t("username_label")}
          </Label>
          <p className="mt-1 font-mono text-sm text-slate-800">{profile.username}</p>
        </div>

        <div>
          <Label className="text-xs uppercase tracking-wider text-slate-600">
            {t("email_label")}
          </Label>
          <p className="mb-1 mt-0.5 text-xs text-slate-500">{t("email_help")}</p>
          <Input value={email} onChange={(e) => setEmail(e.target.value)} type="email" />
          {emailChanged && (
            <p className="mt-1 text-xs text-amber-700">{t("email_change_warning")}</p>
          )}
        </div>

        <div>
          <Label className="text-xs uppercase tracking-wider text-slate-600">
            {t("identity_label")}
          </Label>
          <p className="mb-1 mt-0.5 text-xs text-slate-500">{t("identity_help")}</p>
          <div className="flex gap-2">
            <Input
              value={identity}
              onChange={(e) => setIdentity(e.target.value)}
              placeholder={t("identity_placeholder")}
              className="font-mono text-xs"
            />
            <Button
              type="button"
              variant="outline"
              onClick={() => generate.mutate()}
              disabled={generate.isPending}
            >
              <RefreshCw className="h-4 w-4" />
              <span className="ml-1">{t("generate")}</span>
            </Button>
          </div>
          <p className="mt-1 text-xs text-slate-400">{t("identity_note")}</p>
        </div>

        <div className="flex justify-end border-t pt-3">
          <Button type="button" onClick={() => save.mutate()} disabled={save.isPending}>
            {t("save")}
          </Button>
        </div>
      </section>

      <DensitySection />
    </div>
  );
}

/** Préférence d'affichage locale au navigateur (tokens de densité). */
function DensitySection() {
  const { t } = useTranslation("profile");
  const [density, setDensity] = useState<Density>(getStoredDensity);

  const choose = (value: Density) => {
    applyDensity(value);
    setDensity(value);
  };

  return (
    <section className="density-card space-y-2 rounded-md border bg-white">
      <Label className="text-xs uppercase tracking-wider text-slate-600">
        {t("density_label")}
      </Label>
      <p className="text-xs text-slate-500">{t("density_help")}</p>
      <div className="flex gap-2">
        <Button
          type="button"
          size="sm"
          variant={density === "comfortable" ? "default" : "outline"}
          onClick={() => choose("comfortable")}
        >
          {t("density_comfortable")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant={density === "compact" ? "default" : "outline"}
          onClick={() => choose("compact")}
        >
          {t("density_compact")}
        </Button>
      </div>
    </section>
  );
}
