import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Copy, Check, KeyRound } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";

/** Onglet Api : paramètres de connexion MCP.
 *
 * Les clés d'accès sont personnelles (page Configuration → Clés API) ; ce
 * panneau ne montre que l'endpoint MCP unique + la config Claude Code, et
 * renvoie vers la gestion des clés. Le workspace n'est plus dans l'URL : il se
 * passe en paramètre « workspace » des outils MCP.
 */
export function WorkspaceApiKeysTab() {
  const { t } = useTranslation("apikeys");

  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);

  const publicUrl =
    (import.meta.env["VITE_PUBLIC_URL"] as string | undefined) ?? window.location.origin;
  const mcpUrl = `${publicUrl}/mcp`;
  const mcpConfig = JSON.stringify(
    {
      mcpServers: {
        ragflow: {
          type: "http",
          url: mcpUrl,
          headers: { Authorization: "Bearer <votre-clé>" },
        },
      },
    },
    null,
    2,
  );

  async function copyText(text: string, setCopied: (v: boolean) => void) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <div className="space-y-6">
      <section className="rounded-md border border-slate-200 bg-slate-50 p-4">
        <h3 className="text-sm font-semibold text-slate-800">{t("mcp_section_title")}</h3>
        <div className="mt-3">
          <Label className="text-xs text-slate-500">{t("mcp_url_label")}</Label>
          <div className="mt-1 flex items-center gap-2">
            <Input value={mcpUrl} readOnly className="bg-white font-mono text-xs" />
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void copyText(mcpUrl, setCopiedUrl);
              }}
            >
              {copiedUrl ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
        </div>
        <p className="mt-2 text-xs text-slate-500">{t("mcp_token_hint")}</p>
        <p className="mt-1 text-xs text-slate-500">{t("mcp.workspaces_note")}</p>
        <div className="mt-3">
          <Label className="text-xs text-slate-500">{t("mcp_config_label")}</Label>
          <div className="mt-1 flex items-start gap-2">
            <pre className="flex-1 overflow-x-auto rounded-md border bg-white p-3 font-mono text-xs text-slate-700">
              {mcpConfig}
            </pre>
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                void copyText(mcpConfig, setCopiedConfig);
              }}
            >
              {copiedConfig ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
          </div>
        </div>
      </section>

      <section className="rounded-md border border-sky-200 bg-sky-50 p-4">
        <div className="flex items-start gap-3">
          <KeyRound className="mt-0.5 h-4 w-4 flex-shrink-0 text-sky-600" />
          <div>
            <h3 className="text-sm font-semibold text-sky-900">{t("keys_moved_title")}</h3>
            <p className="mt-1 text-sm text-sky-800">{t("keys_moved_body")}</p>
            <Button asChild variant="outline" size="sm" className="mt-3">
              <Link to="/settings/api-keys">{t("keys_moved_link")}</Link>
            </Button>
          </div>
        </div>
      </section>
    </div>
  );
}
