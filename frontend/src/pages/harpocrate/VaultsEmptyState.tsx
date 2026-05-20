import { KeyRound } from "lucide-react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";

interface VaultsEmptyStateProps {
  onCreate: () => void;
}

export function VaultsEmptyState({ onCreate }: VaultsEmptyStateProps) {
  const { t } = useTranslation("harpocrate");

  return (
    <div className="flex h-full items-center justify-center bg-white">
      <div className="mx-auto max-w-md text-center px-8">
        <KeyRound className="mx-auto mb-4 h-12 w-12 text-slate-400" />
        <h3 className="text-lg font-semibold text-slate-900 mb-2">{t("list.empty_title")}</h3>
        <p className="text-sm text-slate-500 leading-relaxed mb-6">{t("list.empty_subtitle")}</p>
        <Button onClick={onCreate}>{t("list.empty_cta")}</Button>
      </div>
    </div>
  );
}
