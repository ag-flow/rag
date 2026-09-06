import { useTranslation } from "react-i18next";
import { Check } from "lucide-react";

import { usePublicStats } from "@/hooks/usePublicInfo";

/** Panneau gauche de l'écran de connexion (feature 2ca3ceb8) : présentation
 * produit sur fond neutre sombre. Masqué sous 900 px de large. */
export function HeroPanel() {
  const { t } = useTranslation("login");
  const { data: stats } = usePublicStats();

  const args = [1, 2, 3, 4].map((n) => ({
    title: t(`hero.arg${n}_title`),
    text: t(`hero.arg${n}_text`),
  }));

  return (
    <aside className="hidden w-[44%] flex-col justify-between bg-slate-800 p-10 text-white min-[900px]:flex">
      <div className="flex items-center gap-2.5">
        <div className="h-7 w-7 rounded-sm bg-accent-500" aria-hidden="true" />
        <span className="font-display text-xl font-semibold tracking-wide">{t("app_name")}</span>
      </div>

      <div className="space-y-8">
        <div>
          <h1 className="font-display text-3xl font-semibold leading-tight">{t("hero.tagline")}</h1>
          <p className="mt-2 text-sm text-slate-300">{t("hero.subtitle")}</p>
        </div>

        <ul className="space-y-4">
          {args.map((arg) => (
            <li key={arg.title} className="flex gap-3">
              <Check className="mt-0.5 h-4 w-4 flex-shrink-0 text-accent-300" aria-hidden="true" />
              <div>
                <p className="text-sm font-semibold">{arg.title}</p>
                <p className="text-xs leading-relaxed text-slate-300">{arg.text}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>

      <div className="grid grid-cols-2 divide-x divide-slate-600 border border-slate-600">
        <MetricCell value={stats?.indexed_documents ?? null} label={t("hero.metric_documents")} />
        <MetricCell value={stats?.workspaces ?? null} label={t("hero.metric_workspaces")} />
      </div>
    </aside>
  );
}

/** Cellule de métrique — valeur servie par l'API, cellule vide si l'appel
 * échoue (dégradation silencieuse, critère de la fiche). */
function MetricCell({ value, label }: { value: number | null; label: string }) {
  return (
    <div className="px-4 py-3">
      <p className="font-display text-2xl font-semibold text-white">
        {value != null ? value.toLocaleString() : "—"}
      </p>
      <p className="text-xs uppercase tracking-wider text-slate-400">{label}</p>
    </div>
  );
}
