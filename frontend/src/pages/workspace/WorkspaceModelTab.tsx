import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import type { Workspace } from "@/lib/workspaces.types";

interface Props {
  workspace: Workspace;
}

export function WorkspaceModelTab({ workspace }: Props) {
  const { t } = useTranslation("workspace");
  const { provider, model, api_key_ref, base_url } = workspace.indexer;

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-slate-900">{t("model.title")}</h3>
      <dl className="grid grid-cols-2 gap-2 text-sm">
        <dt className="text-slate-500">{t("model.provider")}</dt>
        <dd className="font-mono">{provider}</dd>
        <dt className="text-slate-500">{t("model.model")}</dt>
        <dd className="font-mono">{model}</dd>
        <dt className="text-slate-500">{t("model.base_url")}</dt>
        <dd className="font-mono">{base_url ?? "—"}</dd>
        <dt className="text-slate-500">{t("model.api_key_ref")}</dt>
        <dd className="font-mono">{api_key_ref ?? "—"}</dd>
      </dl>
      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <Info className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("model.immutableNote")}</p>
      </div>
    </div>
  );
}
