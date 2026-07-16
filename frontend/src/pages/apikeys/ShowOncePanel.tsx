import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

interface Props {
  apiKey: string;
}

/** Affichage unique d'une clé fraîchement créée/rotationnée, avec copie. */
export function ShowOncePanel({ apiKey }: Props) {
  const { t } = useTranslation("apikeys");
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(apiKey);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="rounded-md border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-medium text-amber-900">{t("created_key_title")}</p>
      <p className="mt-1 text-xs text-amber-800">{t("created_key_warning")}</p>
      <div className="mt-2 flex items-center gap-2">
        <Input value={apiKey} readOnly className="flex-1 bg-white font-mono text-xs" />
        <Button type="button" variant="outline" onClick={() => void copy()}>
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          <span className="ml-1">{t("copy_btn")}</span>
        </Button>
      </div>
    </div>
  );
}
