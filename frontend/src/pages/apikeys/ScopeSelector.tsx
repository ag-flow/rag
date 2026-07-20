import { useTranslation } from "react-i18next";
import { cn } from "@/lib/utils";
import type { KeyScope } from "@/lib/user-api-keys.types";

const SCOPES: KeyScope[] = ["read", "read_write", "admin"];

interface Props {
  value: KeyScope;
  onChange: (scope: KeyScope) => void;
}

/** Sélecteur du niveau d'accès d'une clé API (3 niveaux exclusifs). */
export function ScopeSelector({ value, onChange }: Props) {
  const { t } = useTranslation("apikeys");

  return (
    <div className="space-y-2" role="radiogroup" aria-label={t("scope.title")}>
      {SCOPES.map((scope) => {
        const checked = value === scope;
        return (
          <label
            key={scope}
            className={cn(
              "flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors",
              checked
                ? "border-sky-400 bg-sky-50"
                : "border-slate-200 hover:border-slate-300",
            )}
          >
            <input
              type="radio"
              name="key-scope"
              value={scope}
              checked={checked}
              onChange={() => onChange(scope)}
              className="mt-0.5"
            />
            <span>
              <span className="block text-sm font-medium text-slate-800">
                {t(`scope.levels.${scope}.label`)}
              </span>
              <span className="block text-xs text-slate-500">
                {t(`scope.levels.${scope}.help`)}
              </span>
            </span>
          </label>
        );
      })}
    </div>
  );
}
