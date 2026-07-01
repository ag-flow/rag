import { useState } from "react";
import { useTranslation } from "react-i18next";
import { ChevronDown, ChevronRight } from "lucide-react";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useDocumentView } from "@/hooks/useIndexKeys";
import type { SectionEntry } from "@/lib/workspaces.types";

const BORDER_COLORS = [
  "border-l-sky-400",
  "border-l-violet-400",
  "border-l-emerald-400",
  "border-l-amber-400",
  "border-l-rose-400",
  "border-l-indigo-400",
] as const;

type BorderColor = (typeof BORDER_COLORS)[number];

const getBorderColor = (i: number): BorderColor =>
  BORDER_COLORS[i % BORDER_COLORS.length] ?? "border-l-sky-400";

interface Props {
  workspaceName: string;
  path: string;
}

export function DocumentChunkViewer({ workspaceName, path }: Props) {
  const { t } = useTranslation("workspace");
  const { data, isLoading, isError } = useDocumentView(workspaceName, path, true);
  const [expandedSections, setExpandedSections] = useState<Set<number>>(new Set());

  const toggleSection = (idx: number) => {
    setExpandedSections((prev) => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx);
      else next.add(idx);
      return next;
    });
  };

  if (isLoading) return <LoadingSpinner />;
  if (isError || !data) {
    return (
      <p className="text-xs text-red-500 py-2">{t("index.document_view.error")}</p>
    );
  }

  return (
    <div className="space-y-1">
      {data.is_legacy && (
        <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded px-2 py-1">
          {t("index.document_view.legacy_notice")}
        </p>
      )}
      {data.sections.map((section, i) => (
        <SectionBlock
          key={`${section.section_index}-${section.section_key}`}
          section={section}
          colorClass={getBorderColor(i)}
          isChunksExpanded={expandedSections.has(i)}
          onToggleChunks={() => toggleSection(i)}
        />
      ))}
    </div>
  );
}

interface SectionBlockProps {
  section: SectionEntry;
  colorClass: BorderColor;
  isChunksExpanded: boolean;
  onToggleChunks: () => void;
}

function SectionBlock({
  section,
  colorClass,
  isChunksExpanded,
  onToggleChunks,
}: SectionBlockProps) {
  const { t } = useTranslation("workspace");
  const chunkCount = section.chunks.length;

  return (
    <div
      className={`border-l-4 ${colorClass} rounded-r border border-l-0 border-slate-200 bg-white`}
    >
      <div className="flex items-center justify-between gap-2 px-3 pt-2 pb-1">
        <span className="font-mono text-xs text-slate-500">
          <span className="font-semibold">§{section.section_index}</span>{" "}
          <span className="text-slate-700">{section.section_key}</span>
        </span>
        {chunkCount > 0 && (
          <button
            type="button"
            onClick={onToggleChunks}
            className="flex shrink-0 items-center gap-1 text-xs text-slate-400 hover:text-slate-700"
          >
            {isChunksExpanded ? (
              <ChevronDown className="h-3 w-3" />
            ) : (
              <ChevronRight className="h-3 w-3" />
            )}
            {t("index.document_view.chunks_count", { count: chunkCount })}
          </button>
        )}
      </div>

      <pre className="px-3 pb-2 font-mono text-xs text-slate-700 whitespace-pre-wrap break-words">
        {section.content}
      </pre>

      {isChunksExpanded && (
        <div className="border-t border-slate-100 bg-slate-50 px-3 py-2 space-y-2">
          <p className="text-xs font-semibold text-slate-500">
            {t("index.document_view.embed_chunks_title", { count: chunkCount })}
          </p>
          {section.chunks.map((chunk) => (
            <div
              key={chunk.chunk_index}
              className="rounded border border-slate-200 bg-white p-2"
            >
              <p className="mb-1 text-xs font-medium text-slate-400">
                {t("index.document_view.embed_chunk_label", { index: chunk.chunk_index })}
              </p>
              <pre className="font-mono text-xs text-slate-700 whitespace-pre-wrap break-words">
                {chunk.embed_text}
              </pre>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
