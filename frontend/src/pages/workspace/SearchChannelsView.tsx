import { useTranslation } from "react-i18next";
import type { ChannelHit, SearchHit } from "@/lib/search-config.types";

const formatScore = (score: number) => score.toFixed(4);

interface ChannelListProps {
  title: string;
  hits: ChannelHit[];
}

function ChannelList({ title, hits }: ChannelListProps) {
  const { t } = useTranslation("playground");

  return (
    <section className="rounded-md border bg-white p-3">
      <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-600">{title}</h4>
      {hits.length === 0 ? (
        <p className="mt-2 text-xs text-slate-400">{t("search.empty_channel")}</p>
      ) : (
        <ol aria-label={title} className="mt-2 space-y-1.5">
          {hits.map((hit) => (
            <li key={`${hit.path}#${hit.chunk_index}`} className="text-xs">
              <span className="font-mono text-slate-500">
                {t("search.rank", { rank: hit.rank })}
              </span>{" "}
              <span className="font-mono text-slate-800 break-all">
                {hit.path}#{hit.chunk_index}
              </span>
              <span className="ml-1 text-slate-400">{formatScore(hit.score)}</span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

interface Props {
  hits: SearchHit[];
  vectorChannel: ChannelHit[];
  lexicalChannel: ChannelHit[];
}

export function SearchChannelsView({ hits, vectorChannel, lexicalChannel }: Props) {
  const { t } = useTranslation("playground");
  const fusionTitle = t("search.sections.fusion");

  return (
    <div className="grid gap-3 md:grid-cols-3">
      <section className="rounded-md border bg-white p-3">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-600">
          {fusionTitle}
        </h4>
        {hits.length === 0 ? (
          <p className="mt-2 text-xs text-slate-400">{t("search.empty_channel")}</p>
        ) : (
          <ol aria-label={fusionTitle} className="mt-2 space-y-2">
            {hits.map((hit) => (
              <li key={`${hit.path}#${hit.chunk_index}`} className="text-xs">
                <div>
                  <span className="font-mono text-slate-800 break-all">
                    {hit.path}#{hit.chunk_index}
                  </span>
                  <span className="ml-1 text-slate-400">{formatScore(hit.score)}</span>
                </div>
                <p className="mt-0.5 line-clamp-3 text-slate-500">{hit.content}</p>
              </li>
            ))}
          </ol>
        )}
      </section>
      <ChannelList title={t("search.sections.vector")} hits={vectorChannel} />
      <ChannelList title={t("search.sections.lexical")} hits={lexicalChannel} />
    </div>
  );
}
