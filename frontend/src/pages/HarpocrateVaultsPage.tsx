import { useTranslation } from "react-i18next";

export function HarpocrateVaultsPage() {
  const { t } = useTranslation("harpocrate");

  return (
    <div className="flex h-full bg-slate-50">
      <div className="p-6 text-slate-600">
        <h1 className="text-xl font-semibold text-slate-900">{t("page.title")}</h1>
        <p className="text-sm text-slate-500 mt-1">{t("page.subtitle")}</p>
        <p className="text-xs text-slate-400 italic mt-4">
          (squelette — composants à venir en T4-T10)
        </p>
      </div>
    </div>
  );
}
