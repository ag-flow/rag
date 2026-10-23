import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "@/hooks/useToast";

const KNOWN_RETURN_ERRORS = new Set([
  "name_taken_key_not_saved",
  "client_not_declared",
  "redirect_uri_not_declared",
  "harpocrate_unreachable",
  "exchange_failed",
  "denied",
  "state_unknown",
  "already_used",
  "harpocrate_dek_missing",
]);

/**
 * Retour du parcours « Connecter à Harpocrate » : le backend redirige vers
 * cette page avec `connect=ok|reconnected&vault=…&tested=…`,
 * `connect=confirm_wallet&vault=…&request=…` (reconnexion vers un autre
 * wallet, à confirmer) ou `connect_error=<raison>`.
 * On traite le retour une fois, puis on retire ces paramètres de l'URL
 * (en gardant `vault`, qui sélectionne le coffre) pour qu'un
 * rafraîchissement ne le rejoue pas. La demande à confirmer est rendue à
 * l'appelant, qui ouvre le dialogue de confirmation.
 */
export function useConnectReturn() {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const outcome = searchParams.get("connect");
  const error = searchParams.get("connect_error");
  const tested = searchParams.get("tested");
  const [pendingRequestId, setPendingRequestId] = useState<string | null>(null);

  useEffect(() => {
    if (!outcome && !error) return;
    if (outcome === "ok" || outcome === "reconnected") {
      const prefix = outcome === "ok" ? "connected" : "reconnected";
      toast(
        tested === "true"
          ? { title: t(`connect.${prefix}_toast`) }
          : { title: t(`connect.${prefix}_untested_toast`), variant: "destructive" },
      );
    } else if (outcome === "confirm_wallet") {
      setPendingRequestId(searchParams.get("request"));
    } else if (error) {
      // Raison inconnue : message générique, jamais la valeur brute de l'URL.
      const key = KNOWN_RETURN_ERRORS.has(error) ? error : "generic";
      toast({ title: t(`connect.errors.${key}`), variant: "destructive" });
    }
    const vault = searchParams.get("vault");
    setSearchParams(vault ? { vault } : {}, { replace: true });
  }, [outcome, error, tested, searchParams, setSearchParams, t, toast]);

  return { pendingRequestId, clearPending: () => setPendingRequestId(null) };
}
