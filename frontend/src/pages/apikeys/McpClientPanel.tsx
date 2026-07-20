import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
import { Button } from "@/components/ui/button";

export interface McpGrant {
  workspace_id: string;
  workspace_name: string;
  can_read: boolean;
}

interface Props {
  grants: McpGrant[];
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
 * Informations de connexion d'un client MCP à un ou plusieurs workspaces via
 * une clé API. Le transport est le Streamable HTTP standard :
 * `{origin}/mcp/{workspace_id}` + en-tête `Authorization: Bearer <clé>`.
 * Seuls les workspaces avec le grant `can_read` sont exposés (la recherche MCP
 * l'exige).
 */
export function McpClientPanel({ grants, apiKey }: Props) {
  const { t } = useTranslation("apikeys");
  const origin = window.location.origin;
  const key = apiKey ?? KEY_PLACEHOLDER;
  const readable = grants.filter((g) => g.can_read);

  if (readable.length === 0) {
    return <p className="text-xs text-slate-500">{t("mcp.no_read_grant")}</p>;
  }

  const servers = Object.fromEntries(
    readable.map((g) => [
      `ragflow-${g.workspace_name}`,
      {
        type: "http",
        url: `${origin}/mcp/${g.workspace_id}`,
        headers: { Authorization: `Bearer ${key}` },
      },
    ]),
  );
  const config = JSON.stringify({ mcpServers: servers }, null, 2);

  return (
    <div className="space-y-3 rounded-md border bg-white p-4">
      <div>
        <p className="text-sm font-medium text-slate-800">{t("mcp.title")}</p>
        <p className="mt-0.5 text-xs text-slate-500">{t("mcp.subtitle")}</p>
      </div>

      {readable.map((g) => (
        <CopyBlock
          key={g.workspace_id}
          label={t("mcp.endpoint_for", { workspace: g.workspace_name })}
          value={`${origin}/mcp/${g.workspace_id}`}
        />
      ))}

      <CopyBlock label={t("mcp.auth_header")} value={`Authorization: Bearer ${key}`} />
      <CopyBlock label={t("mcp.config_json")} value={config} />

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
