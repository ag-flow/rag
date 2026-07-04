import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";
import type { CleaningOptions } from "./CleaningOptionsPanel.schema";
import { CLEANING_KEYS } from "./CleaningOptionsPanel.schema";

interface Props {
  value: CleaningOptions;
  onChange: (value: CleaningOptions) => void;
  disabled?: boolean;
}

export function CleaningOptionsPanel({ value, onChange, disabled = false }: Props) {
  const { t } = useTranslation("workspace");

  const handleToggle = (key: keyof CleaningOptions, checked: boolean) => {
    onChange({ ...value, [key]: checked });
  };

  return (
    <div className="space-y-2">
      <div>
        <p className="text-sm font-medium text-slate-700">
          {t("chunking.cleaning.title")}
        </p>
        <p className="text-xs text-slate-500 mt-0.5">
          {t("chunking.cleaning.description")}
        </p>
      </div>

      <div className="space-y-0 rounded-md border bg-white divide-y divide-slate-100">
        {CLEANING_KEYS.map((key) => (
          <div key={key} className="flex items-start gap-3 px-3 py-3">
            <Switch
              id={`cleaning-${key}`}
              checked={value[key]}
              onCheckedChange={(checked) => handleToggle(key, checked)}
              disabled={disabled}
              className="mt-0.5 shrink-0"
            />
            <label htmlFor={`cleaning-${key}`} className="cursor-pointer min-w-0">
              <span className="block text-sm font-medium text-slate-700 leading-tight">
                {t(`chunking.cleaning.options.${key}.label`)}
              </span>
              <span className="block text-xs text-slate-500 mt-0.5 leading-relaxed">
                {t(`chunking.cleaning.options.${key}.description`)}
              </span>
            </label>
          </div>
        ))}
      </div>
    </div>
  );
}
