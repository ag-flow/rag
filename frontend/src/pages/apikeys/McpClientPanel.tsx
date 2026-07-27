import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

interface Props {
  /** Valeur réelle de la clé (création/rotation). Absente = placeholder de référence. */
  apiKey?: string;
}

const KEY_PLACEHOLDER = "<VOTRE_CLÉ_API>";

function CopyBlock({ label, value }: { label: string; value: string }) {
  const { t } = useTranslation("apikeys");
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(value);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-slate-600">{label}</span>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-6 px-1"
          onClick={() => void copy()}
          aria-label={t("mcp.copy")}
        >
          {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
        </Button>
      </div>
      <pre className="mt-1 overflow-x-auto rounded border bg-slate-50 p-2 font-mono text-xs text-slate-800">
        {value}
      </pre>
    </div>
  );
}

/**
 * Fiche de connexion d'un client MCP. Le serveur ragflow expose un endpoint
 * unique `{origin}/mcp` (transport Streamable HTTP) ; le workspace n'est plus
 * dans l'URL mais passé en paramètre `workspace` des outils. L'authentification
 * se fait via l'en-tête `Authorization: Bearer <clé>`.
 */
export function McpClientPanel({ apiKey }: Props) {
  const { t } = useTranslation("apikeys");
  const origin = window.location.origin;
  const key = apiKey ?? KEY_PLACEHOLDER;
  const endpoint = `${origin}/mcp`;

  const config = JSON.stringify(
    {
      mcpServers: {
        ragflow: {
          type: "http",
          url: endpoint,
          headers: { Authorization: `Bearer ${key}` },
        },
      },
    },
    null,
    2,
  );

  return (
    <div className="space-y-3 rounded-md border bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">{t("mcp.title")}</p>
        <p className="mt-0.5 text-xs text-slate-500">{t("mcp.subtitle")}</p>
      </div>

      <CopyBlock label={t("mcp.endpoint")} value={endpoint} />
      <CopyBlock label={t("mcp.auth_header")} value={`Authorization: Bearer ${key}`} />
      <CopyBlock label={t("mcp.config_json")} value={config} />

      <div className="rounded-md border border-sky-200 bg-sky-50 px-3 py-2 text-xs text-sky-900">
        {t("mcp.workspaces_note")}
      </div>

      <p className="text-xs text-slate-400">
        {t("mcp.contract_hint")}{" "}
        <a className="underline" href="/api/contracts/mcp-tools" target="_blank" rel="noreferrer">
          /api/contracts/mcp-tools
        </a>
      </p>
      {apiKey === undefined && (
        <p className="text-xs text-amber-700">{t("mcp.placeholder_note")}</p>
      )}
    </div>
  );
}
