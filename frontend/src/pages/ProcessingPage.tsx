import { useTranslation } from "react-i18next";

import { WorkerSlotsPanel } from "@/pages/processing/WorkerSlotsPanel";
import { LoadGatePanel } from "@/pages/push/LoadGatePanel";

/** Écran Configuration → Traitement (admin uniquement) : réglages globaux
 * d'exécution des jobs — slots du worker et gate de charge serveur. */
export function ProcessingPage() {
  const { t } = useTranslation("processing");

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("description")}</p>
      </div>
      <WorkerSlotsPanel />
      <LoadGatePanel />
    </div>
  );
}
