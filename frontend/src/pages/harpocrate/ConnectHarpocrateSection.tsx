import { useState } from "react";
import type { UseFormReturn } from "react-hook-form";
import { useMutation } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/lib/api";
import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";
import type { VaultIdentity } from "@/lib/harpocrate-vaults.types";
import type { VaultCreateForm } from "@/lib/validators";

interface ConnectHarpocrateSectionProps {
  form: UseFormReturn<VaultCreateForm>;
  onDekMissing: () => void;
}

/** Raisons de refus renvoyées par le backend au départ (détail du 409). */
const KNOWN_START_ERRORS = new Set([
  "name_taken",
  "https_required",
  "client_not_declared",
  "redirect_uri_not_declared",
  "harpocrate_unreachable",
  "exchange_failed",
]);

/** Ce qu'il faut déclarer chez Harpocrate, renvoyé avec les refus de déclaration. */
interface Declaration {
  client_id: string;
  redirect_uri: string;
}

/** Le 409 porte soit une raison seule, soit `{reason, client_id, redirect_uri}`. */
function parseStartError(err: unknown): { key: string; declaration: Declaration | null } {
  const detail = err instanceof ApiError ? (err.body as { detail?: unknown } | null)?.detail : null;
  if (typeof detail === "string") {
    return { key: KNOWN_START_ERRORS.has(detail) ? detail : "generic", declaration: null };
  }
  if (detail && typeof detail === "object") {
    const d = detail as Partial<Declaration> & { reason?: unknown };
    if (typeof d.reason === "string" && KNOWN_START_ERRORS.has(d.reason)) {
      const declaration =
        typeof d.client_id === "string" && typeof d.redirect_uri === "string"
          ? { client_id: d.client_id, redirect_uri: d.redirect_uri }
          : null;
      return { key: d.reason, declaration };
    }
  }
  return { key: "generic", declaration: null };
}

/**
 * « Connecter à Harpocrate » : crée le coffre sans saisir l'api_key. Le
 * backend dépose la demande, le navigateur part chez Harpocrate, et le coffre
 * est créé au retour (route de callback) — la clé ne passe jamais par ici.
 */
export function ConnectHarpocrateSection({ form, onDekMissing }: ConnectHarpocrateSectionProps) {
  const { t } = useTranslation("harpocrate");
  const [errorKey, setErrorKey] = useState<string | null>(null);
  const [declaration, setDeclaration] = useState<Declaration | null>(null);
  const start = useMutation({
    mutationFn: (identity: VaultIdentity) => harpocrateVaultsApi.connectStart(identity),
  });

  async function handleConnect() {
    setErrorKey(null);
    setDeclaration(null);
    // Seuls nom, libellé et URL sont requis : la clé viendra de Harpocrate.
    const valid = await form.trigger(["name", "label", "base_url"]);
    if (!valid) return;
    const { name, label, base_url, is_default } = form.getValues();
    try {
      const { browser_url } = await start.mutateAsync({ name, label, base_url, is_default });
      window.location.assign(browser_url);
    } catch (err) {
      if (err instanceof ApiError && err.status === 503) {
        onDekMissing();
        return;
      }
      const parsed = parseStartError(err);
      setErrorKey(parsed.key);
      setDeclaration(parsed.declaration);
    }
  }

  return (
    <div className="space-y-2 rounded border border-slate-200 bg-slate-50 p-3">
      <p className="text-xs text-slate-600">{t("connect.explanation")}</p>
      <Button
        type="button"
        variant="outline"
        onClick={handleConnect}
        disabled={start.isPending}
        className="w-full"
      >
        <Link2 className="mr-2 h-4 w-4" />
        {start.isPending ? t("connect.starting") : t("connect.button")}
      </Button>
      {errorKey && (
        <p role="alert" className="text-sm font-medium text-rose-600">
          {t(`connect.errors.${errorKey}`)}
        </p>
      )}
      {declaration && (
        <dl className="space-y-1 rounded border border-rose-200 bg-white p-2 text-xs text-slate-700">
          <dt className="font-medium">{t("connect.declare_client_id")}</dt>
          <dd className="select-all break-all font-mono">{declaration.client_id}</dd>
          <dt className="font-medium">{t("connect.declare_redirect_uri")}</dt>
          <dd className="select-all break-all font-mono">{declaration.redirect_uri}</dd>
        </dl>
      )}
      <p className="text-center text-xs text-slate-400">{t("connect.or_manual")}</p>
    </div>
  );
}
