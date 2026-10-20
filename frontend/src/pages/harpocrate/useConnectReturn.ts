import { useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { useToast } from "@/hooks/useToast";

const KNOWN_RETURN_ERRORS = new Set([
  "name_taken_key_not_saved",
  "app_not_declared",
  "harpocrate_unreachable",
  "exchange_failed",
  "denied",
  "state_unknown",
  "already_used",
  "harpocrate_dek_missing",
]);

/**
 * Retour du parcours « Connecter à Harpocrate » : le backend redirige vers
 * cette page avec `connect=ok&vault=…&tested=…` ou `connect_error=<raison>`.
 * On affiche le message une fois, puis on retire ces paramètres de l'URL
 * (en gardant `vault`, qui sélectionne le coffre créé) pour qu'un
 * rafraîchissement ne le rejoue pas.
 */
export function useConnectReturn() {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const [searchParams, setSearchParams] = useSearchParams();
  const outcome = searchParams.get("connect");
  const error = searchParams.get("connect_error");
  const tested = searchParams.get("tested");

  useEffect(() => {
    if (!outcome && !error) return;
    if (outcome === "ok") {
      toast(
        tested === "true"
          ? { title: t("connect.connected_toast") }
          : { title: t("connect.connected_untested_toast"), variant: "destructive" },
      );
    } else if (error) {
      // Raison inconnue : message générique, jamais la valeur brute de l'URL.
      const key = KNOWN_RETURN_ERRORS.has(error) ? error : "generic";
      toast({ title: t(`connect.errors.${key}`), variant: "destructive" });
    }
    const vault = searchParams.get("vault");
    setSearchParams(vault ? { vault } : {}, { replace: true });
  }, [outcome, error, tested, searchParams, setSearchParams, t, toast]);
}
