import { useTranslation } from "react-i18next";

export function ModelsPage() {
  const { t } = useTranslation("models");
  return (
    <div className="p-6">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>
      <div className="mt-6 text-slate-500">{t("empty")}</div>
    </div>
  );
}
