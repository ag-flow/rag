import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePlaygroundSearch } from "@/hooks/useSearchConfig";
import { useWorkspaces } from "@/hooks/useWorkspaces";
import { SearchChannelsView } from "@/pages/workspace/SearchChannelsView";

export function McpSearchPage() {
  const { t } = useTranslation("mcp");
  const [workspace, setWorkspace] = useState("");
  const [query, setQuery] = useState("");
  const [topK, setTopK] = useState(10);

  const { data: workspaces = [] } = useWorkspaces();
  const search = usePlaygroundSearch(workspace);
  const data = search.data;

  const runSearch = () => {
    const trimmed = query.trim();
    if (!trimmed || !workspace) return;
    search.mutate({ query: trimmed, top_k: topK });
  };

  return (
    <div className="space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <p className="mt-1 text-sm text-slate-500">{t("description")}</p>
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
        className="flex flex-wrap items-center gap-2"
      >
        <select
          className="border rounded px-2 py-1.5 text-sm"
          aria-label={t("workspace_label")}
          value={workspace}
          onChange={(e) => setWorkspace(e.target.value)}
        >
          <option value="">{t("workspace_placeholder")}</option>
          {workspaces.map((ws) => (
            <option key={ws.id} value={ws.name}>
              {ws.name}
            </option>
          ))}
        </select>
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("query_placeholder")}
          aria-label={t("query_placeholder")}
          className="max-w-md"
        />
        <label htmlFor="mcp-top-k" className="text-sm text-slate-700">
          {t("top_k_label")}
        </label>
        <Input
          id="mcp-top-k"
          type="number"
          min={1}
          max={50}
          value={topK}
          onChange={(e) => setTopK(Number(e.target.value))}
          className="w-20"
        />
        <Button type="submit" disabled={search.isPending || !query.trim() || !workspace}>
          {search.isPending ? t("running") : t("run")}
        </Button>
      </form>

      {search.isError && <p className="text-sm text-rose-600">{t("error")}</p>}

      {data && (
        <>
          {!data.hybrid_enabled && (
            <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 flex gap-2 text-sm">
              <Info className="h-4 w-4 text-sky-600 mt-0.5 flex-shrink-0" />
              <p className="text-sky-900">{t("hybrid_disabled")}</p>
            </div>
          )}

          <SearchChannelsView
            hits={data.hits}
            vectorChannel={data.vector_channel}
            lexicalChannel={data.lexical_channel}
          />
        </>
      )}

      <p className="text-xs text-slate-400">
        {t("mcp_note")}{" "}
        <a
          href="/api/contracts/mcp-tools"
          target="_blank"
          rel="noreferrer"
          className="underline hover:text-slate-600"
        >
          {t("mcp_contract_link")}
        </a>
      </p>
    </div>
  );
}
