import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Info } from "lucide-react";
import type { ChunkingConfig } from "@/lib/chunking.types";
import { ChunkingEngineSwitch } from "./ChunkingEngineSwitch";
import { DefaultStrategyPanel } from "./DefaultStrategyPanel";

interface Props {
  workspaceName: string;
  config: ChunkingConfig;
}

/**
 * Vue du moteur `structured` (cible) : binding de la stratégie par défaut,
 * carte d'info renvoyant vers le catalogue (/chunking-strategies) et l'onglet
 * Triggers, et bascule discrète de retour vers le moteur legacy.
 */
export function ChunkingStructuredView({ workspaceName, config }: Props) {
  const { t } = useTranslation("workspace");

  return (
    <div className="space-y-4">
      <span className="inline-flex items-center gap-1.5 rounded-full border border-slate-200 bg-slate-50 px-2.5 py-0.5 text-xs font-medium text-slate-600">
        <span className="h-2 w-2 rounded-full bg-emerald-500" />
        {t("chunking.engine.badgeStructured")}
      </span>

      <DefaultStrategyPanel
        workspaceName={workspaceName}
        defaultStrategyId={config.default_strategy_id}
      />

      <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 flex gap-2 text-sm">
        <Info className="h-4 w-4 text-slate-500 mt-0.5 flex-shrink-0" />
        <div className="space-y-1 text-slate-700">
          <p>{t("chunking.engine.structuredInfo.body")}</p>
          <p>
            <Link
              to="/chunking-strategies"
              className="font-medium text-slate-900 underline underline-offset-2"
            >
              {t("chunking.engine.structuredInfo.link")}
            </Link>
          </p>
        </div>
      </div>

      <div className="flex justify-end pt-2">
        <ChunkingEngineSwitch
          workspaceName={workspaceName}
          targetEngine="legacy"
          variant="ghost"
        />
      </div>
    </div>
  );
}
