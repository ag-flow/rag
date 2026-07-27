import { useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Info } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { usePlaygroundSearch } from "@/hooks/useSearchConfig";
import { simulateRrf } from "@/lib/rrf";
import { SearchChannelsView } from "./SearchChannelsView";

const asPercent = (value: number) => `${Math.round(value * 100)} %`;

interface SimulationWeights {
  vector: number;
  lexical: number;
}

interface Props {
  workspaceName: string;
}

export function PlaygroundSearchTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const search = usePlaygroundSearch(workspaceName);
  const [query, setQuery] = useState("");
  const [weights, setWeights] = useState<SimulationWeights | null>(null);

  const data = search.data;

  const runSearch = () => {
    const trimmed = query.trim();
    if (!trimmed) return;
    search.mutate(
      { query: trimmed },
      {
        onSuccess: (res) => {
          // Curseurs de simulation initialisés aux poids serveur de la réponse.
          setWeights({ vector: res.weight_vector, lexical: res.weight_lexical });
        },
      },
    );
  };

  const simulated = useMemo(() => {
    if (!data || !weights) return [];
    return simulateRrf(
      data.vector_channel,
      data.lexical_channel,
      data.rrf_k,
      weights.vector,
      weights.lexical,
    );
  }, [data, weights]);

  const simulationTitle = t("search.simulation.resultTitle");

  return (
    <div className="space-y-4">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          runSearch();
        }}
        className="flex gap-2"
      >
        <Input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder={t("search.query_placeholder")}
          aria-label={t("search.query_placeholder")}
          className="max-w-md"
        />
        <Button type="submit" disabled={search.isPending || !query.trim()}>
          {search.isPending ? t("search.running") : t("search.run")}
        </Button>
      </form>

      {search.isError && <p className="text-sm text-rose-600">{t("search.error")}</p>}

      {data && (
        <>
          {!data.hybrid_enabled && (
            <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 flex gap-2 text-sm">
              <Info className="h-4 w-4 text-sky-600 mt-0.5 flex-shrink-0" />
              <p className="text-sky-900">{t("search.hybrid_disabled")}</p>
            </div>
          )}

          <SearchChannelsView
            hits={data.hits}
            vectorChannel={data.vector_channel}
            lexicalChannel={data.lexical_channel}
          />

          {weights && (
            <section className="rounded-md border bg-white p-4 space-y-3">
              <div>
                <h4 className="text-sm font-semibold text-slate-900">
                  {t("search.simulation.title")}
                </h4>
                <p className="mt-1 text-xs text-slate-500">{t("search.simulation.description")}</p>
              </div>

              <div className="grid gap-3 md:grid-cols-2">
                <div>
                  <label htmlFor="sim-weight-vector" className="text-sm text-slate-700">
                    {t("search.simulation.weightVector")}
                    <span className="ml-2 font-mono text-xs text-slate-500">
                      {asPercent(weights.vector)}
                    </span>
                  </label>
                  <input
                    id="sim-weight-vector"
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={weights.vector}
                    onChange={(e) => setWeights({ ...weights, vector: Number(e.target.value) })}
                    className="mt-1 block w-full"
                    aria-label={t("search.simulation.weightVector")}
                  />
                </div>
                <div>
                  <label htmlFor="sim-weight-lexical" className="text-sm text-slate-700">
                    {t("search.simulation.weightLexical")}
                    <span className="ml-2 font-mono text-xs text-slate-500">
                      {asPercent(weights.lexical)}
                    </span>
                  </label>
                  <input
                    id="sim-weight-lexical"
                    type="range"
                    min={0}
                    max={1}
                    step={0.05}
                    value={weights.lexical}
                    onChange={(e) => setWeights({ ...weights, lexical: Number(e.target.value) })}
                    className="mt-1 block w-full"
                    aria-label={t("search.simulation.weightLexical")}
                  />
                </div>
              </div>

              <div>
                <h5 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
                  {simulationTitle}
                </h5>
                {simulated.length === 0 ? (
                  <p className="mt-2 text-xs text-slate-400">{t("search.empty_channel")}</p>
                ) : (
                  <ol aria-label={simulationTitle} className="mt-2 space-y-1.5">
                    {simulated.map((hit) => (
                      <li key={`${hit.path}#${hit.chunk_index}`} className="text-xs">
                        <span className="font-mono text-slate-800 break-all">
                          {hit.path}#{hit.chunk_index}
                        </span>
                        <span className="ml-1 text-slate-400">{hit.score.toFixed(4)}</span>
                      </li>
                    ))}
                  </ol>
                )}
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
