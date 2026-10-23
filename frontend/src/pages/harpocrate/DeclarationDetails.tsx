import { useTranslation } from "react-i18next";
import type { Declaration } from "@/pages/harpocrate/connectStartError";

interface DeclarationDetailsProps {
  declaration: Declaration;
}

/** Ce qu'un admin Harpocrate doit déclarer, au caractère près (valeurs publiques). */
export function DeclarationDetails({ declaration }: DeclarationDetailsProps) {
  const { t } = useTranslation("harpocrate");
  return (
    <dl className="space-y-1 rounded border border-rose-200 bg-white p-2 text-xs text-slate-700">
      <dt className="font-medium">{t("connect.declare_client_id")}</dt>
      <dd className="select-all break-all font-mono">{declaration.client_id}</dd>
      <dt className="font-medium">{t("connect.declare_redirect_uri")}</dt>
      <dd className="select-all break-all font-mono">{declaration.redirect_uri}</dd>
    </dl>
  );
}
