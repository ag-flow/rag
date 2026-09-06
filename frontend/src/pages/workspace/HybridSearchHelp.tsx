import { useTranslation } from "react-i18next";
import { BookOpen } from "lucide-react";

// Article « 18 — Recherche hybride » du manuel produit (docflow, workspace
// ragflow / bloc documentation).
const DOC_URL =
  "https://doc.yoops.org/ws/ragflow/blocs/documentation/documents/de40ecfa-05d8-4de2-89b3-6fb142acdd01";

/** Documentation ponctuelle de la recherche hybride : ce que c'est, ce que ça
 * apporte, ce que l'activation déclenche — avec lien vers le manuel produit. */
export function HybridSearchHelp() {
  const { t } = useTranslation("workspace");
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 px-4 py-3 space-y-2 text-sm">
      <p className="font-medium text-slate-800">{t("search.help.title")}</p>
      <p className="text-slate-600">{t("search.help.what")}</p>
      <p className="text-slate-600">{t("search.help.activation")}</p>
      <a
        href={DOC_URL}
        target="_blank"
        rel="noreferrer"
        className="inline-flex items-center gap-1.5 text-sky-700 hover:underline underline-offset-2"
      >
        <BookOpen className="h-3.5 w-3.5" />
        {t("search.help.doc_link")}
      </a>
    </div>
  );
}
