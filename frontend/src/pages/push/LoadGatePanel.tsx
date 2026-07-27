import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useLoadGate, useSetLoadGate } from "@/hooks/useLoadGate";
import { useToast } from "@/hooks/useToast";

function metricLine(
  label: string,
  value: number | null,
  threshold: number,
  unknownLabel: string,
): string {
  const measured = value != null ? `${value} %` : unknownLabel;
  return `${label} : ${measured} (seuil ${threshold} %)`;
}

/** Gate de charge serveur : quand la pression CPU (PSI) ou la mémoire dépasse
 * les seuils, le worker suspend le pick de nouveaux jobs — la file attend, rien
 * n'est rejeté. Seuils persistés dans admin.env (relu à chaud). */
export function LoadGatePanel() {
  const { t } = useTranslation("push");
  const { toast } = useToast();
  const { data: status } = useLoadGate();
  const setGate = useSetLoadGate();

  const [enabled, setEnabled] = useState(true);
  const [cpuPct, setCpuPct] = useState("40");
  const [memPct, setMemPct] = useState("85");
  const [ioPct, setIoPct] = useState("60");

  useEffect(() => {
    if (!status) return;
    setEnabled(status.enabled);
    setCpuPct(String(status.cpu_threshold_pct));
    setMemPct(String(status.memory_threshold_pct));
    setIoPct(String(status.io_threshold_pct));
  }, [status]);

  if (!status) return null;

  const badge = !status.enabled
    ? { label: t("load_gate.badge_disabled"), cls: "bg-slate-100 text-slate-500" }
    : status.overloaded
      ? { label: t("load_gate.badge_paused"), cls: "bg-amber-50 text-amber-700" }
      : { label: t("load_gate.badge_normal"), cls: "bg-emerald-50 text-emerald-700" };

  const intOr = (v: string, dflt: number): number => {
    const n = Number(v.trim());
    return Number.isFinite(n) && n >= 1 && n <= 100 ? Math.floor(n) : dflt;
  };

  const save = () => {
    setGate.mutate(
      {
        enabled,
        cpu_threshold_pct: intOr(cpuPct, status.cpu_threshold_pct),
        memory_threshold_pct: intOr(memPct, status.memory_threshold_pct),
        io_threshold_pct: intOr(ioPct, status.io_threshold_pct),
      },
      {
        onSuccess: () => toast({ title: t("load_gate.saved") }),
        onError: () => toast({ title: t("load_gate.error"), variant: "destructive" }),
      },
    );
  };

  return (
    <section className="rounded-md border bg-white p-4">
      <div className="flex items-center justify-between gap-4">
        <h2 className="text-sm font-semibold text-slate-900">{t("load_gate.title")}</h2>
        <span
          className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${badge.cls}`}
        >
          {badge.label}
        </span>
      </div>
      <p className="mt-1 text-xs text-slate-500">{t("load_gate.help")}</p>
      <p className="mt-2 font-mono text-xs text-slate-600">
        {metricLine(
          t("load_gate.cpu_metric"),
          status.cpu_psi_avg60,
          status.cpu_threshold_pct,
          t("load_gate.unknown"),
        )}
        {" — "}
        {metricLine(
          t("load_gate.memory_metric"),
          status.memory_used_pct,
          status.memory_threshold_pct,
          t("load_gate.unknown"),
        )}
        {" — "}
        {metricLine(
          t("load_gate.io_metric"),
          status.io_psi_avg60,
          status.io_threshold_pct,
          t("load_gate.unknown"),
        )}
      </p>
      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="flex items-center gap-2">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            aria-label={t("load_gate.enabled_label")}
          />
          <span className="text-xs text-slate-600">{t("load_gate.enabled_label")}</span>
        </div>
        <div>
          <Label className="text-xs text-slate-600">{t("load_gate.cpu_threshold")}</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={cpuPct}
            onChange={(e) => setCpuPct(e.target.value)}
            className="mt-1 w-24"
            aria-label={t("load_gate.cpu_threshold")}
          />
        </div>
        <div>
          <Label className="text-xs text-slate-600">{t("load_gate.memory_threshold")}</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={memPct}
            onChange={(e) => setMemPct(e.target.value)}
            className="mt-1 w-24"
            aria-label={t("load_gate.memory_threshold")}
          />
        </div>
        <div>
          <Label className="text-xs text-slate-600">{t("load_gate.io_threshold")}</Label>
          <Input
            type="number"
            min={1}
            max={100}
            value={ioPct}
            onChange={(e) => setIoPct(e.target.value)}
            className="mt-1 w-24"
            aria-label={t("load_gate.io_threshold")}
          />
        </div>
        <Button type="button" size="sm" onClick={save} disabled={setGate.isPending}>
          {t("load_gate.submit")}
        </Button>
      </div>
    </section>
  );
}
