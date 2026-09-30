import { useTranslation } from "react-i18next";

import { useLoadGate } from "@/hooks/useLoadGate";
import { formatRelativeTime } from "@/lib/relativeTime";

interface Props {
  hasPendingJobs: boolean;
}

/** Signale, là où l'on regarde ses jobs, que le worker ne les traite plus parce
 * que le gate de charge serveur est déclenché — sans ce bandeau, des jobs
 * `pending` qui ne bougent pas ressemblent à une panne silencieuse. */
export function WorkerPausedBanner({ hasPendingJobs }: Props) {
  const { t } = useTranslation("workspace");
  const { data: gate } = useLoadGate();

  if (!hasPendingJobs || !gate?.worker_paused_since) return null;

  return (
    <div
      role="status"
      className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800"
    >
      <p className="font-semibold">{t("jobs.worker_paused.title")}</p>
      <p className="mt-1">
        {t("jobs.worker_paused.body", {
          since: formatRelativeTime(gate.worker_paused_since, t),
          reasons: gate.reasons.join(", "),
        })}
      </p>
    </div>
  );
}
