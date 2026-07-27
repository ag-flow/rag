import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useChunkingConfig } from "@/hooks/useChunking";
import type { Workspace } from "@/lib/workspaces.types";
import { ChunkingEngineSwitch } from "./ChunkingEngineSwitch";
import { ChunkingLegacyForm } from "./ChunkingLegacyForm";
import { ChunkingStructuredView } from "./ChunkingStructuredView";

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

/**
 * Onglet Chunking du détail workspace. Rendu conditionnel par moteur :
 * - `structured` (cible) : stratégie par défaut du catalogue + carte info,
 *   les paramètres vivent dans les stratégies (/chunking-strategies).
 * - `legacy` : bandeau d'avertissement avec bascule vers structured, puis le
 *   formulaire historique en caractères.
 */
export function WorkspaceChunkingTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading } = useChunkingConfig(workspace.name, enabled);

  if (isLoading || !data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          {t("chunking.title")}
          <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-slate-600">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            {t("chunking.badgeMandatory")}
          </span>
        </h3>
        <p className="mt-1 text-sm text-slate-600">{t("chunking.description")}</p>
      </div>

      {data.engine === "structured" ? (
        <ChunkingStructuredView workspaceName={workspace.name} config={data} />
      ) : (
        <>
          <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-sm space-y-2">
            <div className="flex gap-2">
              <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
              <p className="text-amber-900">{t("chunking.engine.legacyBanner")}</p>
            </div>
            <div className="flex justify-end">
              <ChunkingEngineSwitch workspaceName={workspace.name} targetEngine="structured" />
            </div>
          </div>
          <ChunkingLegacyForm workspaceName={workspace.name} config={data} />
        </>
      )}
    </div>
  );
}
