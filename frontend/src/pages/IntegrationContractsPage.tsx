import { useState } from "react";
import { useTranslation } from "react-i18next";
import { useQuery } from "@tanstack/react-query";
import { Copy, Check, ExternalLink, FileCode2, ChevronRight } from "lucide-react";
import { Button } from "@/components/ui/button";
import { contractsApi, listEndpoints, listToolParams } from "@/lib/contracts";

const METHOD_COLORS: Record<string, string> = {
  GET: "text-emerald-700 bg-emerald-50",
  POST: "text-sky-700 bg-sky-50",
  PUT: "text-amber-700 bg-amber-50",
  PATCH: "text-amber-700 bg-amber-50",
  DELETE: "text-rose-700 bg-rose-50",
};

/** Liste les endpoints du contrat par clé API (méthode + URL absolue). */
function ApiKeyEndpoints() {
  const { t } = useTranslation("integration");
  const { data, isLoading, isError } = useQuery({
    queryKey: ["contracts", "openapi-apikey"],
    queryFn: contractsApi.getApikeyOpenapi,
  });

  if (isLoading || isError || !data) return null;
  const endpoints = listEndpoints(data, window.location.origin);
  if (endpoints.length === 0) return null;

  return (
    <div className="mt-3 border-t pt-3">
      <p className="text-xs font-medium text-slate-600">{t("endpoints_label")}</p>
      <ul className="mt-2 space-y-1.5">
        {endpoints.map((e) => (
          <li key={`${e.method} ${e.url}`} className="flex items-center gap-2 text-xs">
            <span
              className={`shrink-0 rounded px-1.5 py-0.5 font-mono font-semibold ${METHOD_COLORS[e.method] ?? "text-slate-600 bg-slate-100"}`}
            >
              {e.method}
            </span>
            <code className="overflow-x-auto font-mono text-slate-700">{e.url}</code>
            {e.summary && <span className="truncate text-slate-500">— {e.summary}</span>}
          </li>
        ))}
      </ul>
    </div>
  );
}

interface ContractCardProps {
  title: string;
  description: string;
  url: string;
  /** Libellé du bouton d'ouverture (voir/télécharger selon le contrat). */
  openLabel: string;
  /** URL d'une vue Swagger UI pour ce contrat (bouton « Swagger » si présent). */
  swaggerUrl?: string;
}

/** Explorateur d'outils MCP — équivalent Swagger pour le contrat MCP (non-OpenAPI). */
function McpToolsExplorer() {
  const { t } = useTranslation("integration");
  const [open, setOpen] = useState(false);
  const { data } = useQuery({
    queryKey: ["contracts", "mcp-tools"],
    queryFn: contractsApi.getMcpTools,
    enabled: open, // charge à l'ouverture seulement
  });

  return (
    <div className="mt-3 border-t pt-3">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex items-center gap-1 text-xs font-medium text-slate-600 hover:text-slate-900"
        aria-expanded={open}
      >
        <ChevronRight className={`h-3.5 w-3.5 transition-transform ${open ? "rotate-90" : ""}`} />
        {t("mcp_tools_label")}
        {data ? ` (${data.count})` : ""}
      </button>
      {open && data && (
        <ul className="mt-2 space-y-2">
          {data.tools.map((tool) => (
            <li key={tool.name} className="rounded border border-slate-100 bg-slate-50 p-2">
              <code className="font-mono text-xs font-semibold text-slate-800">{tool.name}</code>
              {tool.description && (
                <p className="mt-0.5 text-xs text-slate-500">
                  {tool.description.split("\n")[0]}
                </p>
              )}
              <div className="mt-1 flex flex-wrap gap-1">
                {listToolParams(tool).map((p) => (
                  <span
                    key={p.name}
                    title={p.description}
                    className="rounded bg-white px-1.5 py-0.5 font-mono text-[11px] text-slate-600"
                  >
                    {p.name}
                    <span className="text-slate-400">:{p.type}</span>
                    {p.required && <span className="ml-0.5 text-rose-500">*</span>}
                  </span>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Contenu d'une carte contrat (sans le cadre) : titre, description, URL + actions. */
function ContractCardInner({ title, description, url, openLabel, swaggerUrl }: ContractCardProps) {
  const { t } = useTranslation("integration");
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <>
      <h3 className="text-sm font-semibold text-slate-900">{title}</h3>
      <p className="mt-1 text-sm text-slate-600">{description}</p>
      <div className="mt-3 flex items-center gap-2">
        <code className="flex-1 overflow-x-auto rounded border bg-slate-50 px-2 py-1.5 font-mono text-xs text-slate-800">
          {url}
        </code>
        <Button type="button" variant="outline" size="sm" onClick={() => void copy()}>
          {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
          <span className="ml-1">{t("copy")}</span>
        </Button>
        <Button asChild variant="outline" size="sm">
          <a href={url} target="_blank" rel="noreferrer">
            <ExternalLink className="h-4 w-4" />
            <span className="ml-1">{openLabel}</span>
          </a>
        </Button>
        {swaggerUrl && (
          <Button asChild variant="outline" size="sm">
            <a href={swaggerUrl} target="_blank" rel="noreferrer">
              <FileCode2 className="h-4 w-4" />
              <span className="ml-1">{t("swagger")}</span>
            </a>
          </Button>
        )}
      </div>
    </>
  );
}

function ContractCard(props: ContractCardProps) {
  return (
    <section className="rounded-md border bg-white p-4">
      <ContractCardInner {...props} />
    </section>
  );
}

/** Menu Intégration : contrats exposés par le service (events workflow, REST, MCP). */
export function IntegrationContractsPage() {
  const { t } = useTranslation("integration");
  const origin = window.location.origin;

  return (
    <div className="mx-auto max-w-4xl p-6">
      <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
      <p className="mt-1 text-sm text-slate-500">{t("page_subtitle")}</p>

      <div className="mt-6 space-y-4">
        <ContractCard
          title={t("events.title")}
          description={t("events.description")}
          url={`${origin}/api/contracts/workflow-events`}
          openLabel={t("view")}
          swaggerUrl={`${origin}/api/contracts/workflow-events/docs`}
        />
        <ContractCard
          title={t("rest.title")}
          description={t("rest.description")}
          url={`${origin}/openapi.json`}
          openLabel={t("view")}
          swaggerUrl={`${origin}/docs`}
        />
        <div className="rounded-md border bg-white p-4">
          <ContractCardInner
            title={t("rest_apikey.title")}
            description={t("rest_apikey.description")}
            url={`${origin}/api/contracts/openapi-apikey`}
            openLabel={t("view")}
            swaggerUrl={`${origin}/api/contracts/openapi-apikey/docs`}
          />
          <ApiKeyEndpoints />
        </div>
        <div className="rounded-md border bg-white p-4">
          <ContractCardInner
            title={t("mcp.title")}
            description={t("mcp.description")}
            url={`${origin}/api/contracts/mcp-tools`}
            openLabel={t("view")}
          />
          <McpToolsExplorer />
        </div>
      </div>
    </div>
  );
}
