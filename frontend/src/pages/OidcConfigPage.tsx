import { useTranslation } from "react-i18next";

export function OidcConfigPage() {
  const { t } = useTranslation("oidc");
  return (
    <div className="p-6 max-w-2xl mx-auto">
      <h1 className="text-xl font-semibold text-slate-900">{t("title")}</h1>
      <p className="text-sm text-slate-500 mt-1">{t("subtitle")}</p>
      <div className="mt-6 text-slate-500">Form (T4)</div>
    </div>
  );
}
