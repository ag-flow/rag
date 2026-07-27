import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useProcessing, useSetProcessing } from "@/hooks/useProcessing";
import { useToast } from "@/hooks/useToast";

/** Slots de jobs concurrents du worker (feature a9719d13) : chaque utilisateur
 * obtient un slot avant qu'un autre n'en prenne un deuxième — plafond machine
 * global, persisté dans admin.env (relu à chaud). */
export function WorkerSlotsPanel() {
  const { t } = useTranslation("processing");
  const { toast } = useToast();
  const { data: status } = useProcessing();
  const setProcessing = useSetProcessing();

  const [maxJobs, setMaxJobs] = useState("2");

  useEffect(() => {
    if (!status) return;
    setMaxJobs(String(status.max_parallel_jobs));
  }, [status]);

  if (!status) return null;

  const intOr = (v: string, dflt: number): number => {
    const n = Number(v.trim());
    return Number.isFinite(n) && n >= 1 && n <= 16 ? Math.floor(n) : dflt;
  };

  const save = () => {
    setProcessing.mutate(
      { max_parallel_jobs: intOr(maxJobs, status.max_parallel_jobs) },
      {
        onSuccess: () => toast({ title: t("worker.saved") }),
        onError: () => toast({ title: t("worker.error"), variant: "destructive" }),
      },
    );
  };

  return (
    <section className="rounded-md border bg-white p-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold text-slate-900">{t("worker.title")}</h2>
        <span className="font-mono text-xs text-slate-600">
          {t("worker.active_jobs", { count: status.active_jobs })}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{t("worker.help")}</p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div>
          <Label className="text-xs text-slate-600">{t("worker.max_label")}</Label>
          <Input
            type="number"
            min={1}
            max={16}
            value={maxJobs}
            onChange={(e) => setMaxJobs(e.target.value)}
            className="mt-1 w-24"
            aria-label={t("worker.max_label")}
          />
        </div>
        <Button type="button" size="sm" onClick={save} disabled={setProcessing.isPending}>
          {t("worker.submit")}
        </Button>
      </div>
    </section>
  );
}
