import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check, ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";

interface ContractCardProps {
  title: string;
  description: string;
  url: string;
  /** Libellé du bouton d'ouverture (voir/télécharger selon le contrat). */
  openLabel: string;
}

function ContractCard({ title, description, url, openLabel }: ContractCardProps) {
  const { t } = useTranslation("integration");
  const [copied, setCopied] = useState(false);

  async function copy() {
    await navigator.clipboard.writeText(url);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

  return (
    <section className="rounded-md border bg-white p-4">
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
      </div>
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
        />
        <ContractCard
          title={t("rest.title")}
          description={t("rest.description")}
          url={`${origin}/openapi.json`}
          openLabel={t("view")}
        />
        <ContractCard
          title={t("rest_apikey.title")}
          description={t("rest_apikey.description")}
          url={`${origin}/api/contracts/openapi-apikey`}
          openLabel={t("view")}
        />
        <ContractCard
          title={t("mcp.title")}
          description={t("mcp.description")}
          url={`${origin}/api/contracts/mcp-tools`}
          openLabel={t("view")}
        />
      </div>
    </div>
  );
}
