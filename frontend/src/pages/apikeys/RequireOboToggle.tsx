import { useTranslation } from "react-i18next";
import { Switch } from "@/components/ui/switch";

interface Props {
  checked: boolean;
  onChange: (checked: boolean) => void;
}

export function RequireOboToggle({ checked, onChange }: Props) {
  const { t } = useTranslation("apikeys");
  return (
    <div className="flex items-start justify-between gap-4 rounded-md border p-3">
      <div>
        <p className="text-sm font-medium text-slate-800">{t("obo.title")}</p>
        <p className="mt-1 text-xs text-slate-500">{t("obo.help")}</p>
      </div>
      <Switch checked={checked} onCheckedChange={onChange} aria-label={t("obo.title")} />
    </div>
  );
}
