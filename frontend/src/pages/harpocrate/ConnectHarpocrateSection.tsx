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
import { parseStartError, type Declaration } from "@/pages/harpocrate/connectStartError";
import { DeclarationDetails } from "@/pages/harpocrate/DeclarationDetails";

interface ConnectHarpocrateSectionProps {
  form: UseFormReturn<VaultCreateForm>;
  onDekMissing: () => void;
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
      {declaration && <DeclarationDetails declaration={declaration} />}
      <p className="text-center text-xs text-slate-400">{t("connect.or_manual")}</p>
    </div>
  );
}
