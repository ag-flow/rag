import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  useChunkingStrategies,
  useCompareChunking,
  usePreviewChunking,
} from "@/hooks/useChunkingStrategies";
import { ApiError } from "@/lib/api";
import type {
  PreviewChunk,
  PreviewRegion,
  PreviewResult,
  StrategyOut,
} from "@/lib/chunking-strategies.types";

const NONE = "__none__";

function RegionsPanel({
  regions,
  strategiesById,
}: {
  regions: PreviewRegion[];
  strategiesById: Map<string, StrategyOut>;
}) {
  const { t } = useTranslation("playground");
  if (regions.length === 0) return null;

  function regionRouteLabel(region: PreviewRegion): string {
    if (!region.routed) return t("chunkPreview.region_inline");
    if (region.overflow_policy === "parent_only") return t("chunkPreview.region_parent_only");
    if (region.target_strategy_id !== null) {
      const target = strategiesById.get(region.target_strategy_id);
      return t("chunkPreview.region_target", {
        label: target?.label ?? region.target_strategy_id,
      });
    }
    if (region.atomic) return t("chunkPreview.region_atomic", { policy: region.overflow_policy });
    return t("chunkPreview.region_inline_explicit");
  }
  return (
    <div className="rounded-md border border-slate-200 bg-slate-50 p-2">
      <p className="mb-1 text-xs font-semibold text-slate-600">
        {t("chunkPreview.regions_title", { count: regions.length })}
      </p>
      <div className="space-y-1">
        {regions.map((region, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2 text-xs">
            <Badge variant={region.routed ? "secondary" : "outline"}>
              {region.region_type}
              {region.qualifier ? `:${region.qualifier}` : ""}
            </Badge>
            <span className="font-mono text-slate-400">
              l.{region.start_line}-{region.end_line}
            </span>
            <span className={region.routed ? "text-sky-700" : "text-slate-500"}>
              {regionRouteLabel(region)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChunkCard({ chunk, missing }: { chunk: PreviewChunk; missing: boolean }) {
  const { t } = useTranslation("playground");
  return (
    <div
      className={
        "rounded-md border p-2 " +
        (missing ? "border-amber-300 bg-amber-50" : "border-slate-200 bg-white")
      }
    >
      <div className="mb-1 flex flex-wrap items-center gap-2 text-xs text-slate-500">
        <span className="font-medium text-slate-700">
          {t("chunkPreview.chunk_title", { index: chunk.index, tokens: chunk.tokens })}
        </span>
        <span className="font-mono">{chunk.parent_key}</span>
        {chunk.region_type !== null && (
          <Badge variant="secondary">
            {chunk.region_type}
            {chunk.region_qualifier ? `:${chunk.region_qualifier}` : ""}
          </Badge>
        )}
        {chunk.inline_context !== null && (
          <Badge variant="outline" className="border-emerald-300 text-emerald-700">
            ctx:{chunk.inline_context}
          </Badge>
        )}
        {missing && <span className="text-amber-700">{t("chunkPreview.only_this_side")}</span>}
      </div>
      <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs text-slate-800">
        {chunk.embed_text}
      </pre>
    </div>
  );
}

function PreviewColumn({
  result,
  missingHashes,
  strategiesById,
}: {
  result: PreviewResult;
  missingHashes: Set<string>;
  strategiesById: Map<string, StrategyOut>;
}) {
  const { t } = useTranslation("playground");
  return (
    <div className="min-w-0 flex-1 space-y-2">
      <div className="text-sm font-medium text-slate-900">
        {result.strategy.label}
        <span className="ml-2 text-xs font-normal text-slate-500">
          {t("chunkPreview.totals", {
            chunks: result.total_chunks,
            tokens: result.total_tokens,
          })}
          {" · "}
          {t("chunkPreview.parents", { count: result.parents.length })}
        </span>
      </div>
      <RegionsPanel regions={result.regions} strategiesById={strategiesById} />
      <div className="space-y-2">
        {result.chunks.map((chunk) => (
          <ChunkCard
            key={chunk.index}
            chunk={chunk}
            missing={missingHashes.has(chunk.chunk_hash)}
          />
        ))}
      </div>
    </div>
  );
}

interface Props {
  workspaceName: string;
}

export function PlaygroundChunkPreviewTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const { data: strategies } = useChunkingStrategies();
  const preview = usePreviewChunking();
  const compare = useCompareChunking();

  const [strategyA, setStrategyA] = useState<string>("");
  const [strategyB, setStrategyB] = useState<string>(NONE);
  const [content, setContent] = useState("");
  const [runPrompts, setRunPrompts] = useState(false);

  const strategiesById = new Map((strategies ?? []).map((s) => [s.id, s]));
  const isComparing = strategyB !== NONE;
  const isPending = preview.isPending || compare.isPending;
  const canRun = strategyA !== "" && content.trim() !== "" && !isPending;

  function handleRun() {
    if (!canRun) return;
    if (isComparing) {
      preview.reset();
      compare.mutate({ strategyA, strategyB, content });
    } else {
      compare.reset();
      preview.mutate({ strategyId: strategyA, content, workspaceName, runPrompts });
    }
  }

  const error = preview.error ?? compare.error;
  const errorMessage =
    error instanceof ApiError && typeof (error.body as { detail?: unknown })?.detail === "string"
      ? (error.body as { detail: string }).detail
      : (error?.message ?? "");

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-4">
        <div className="space-y-1.5">
          <Label>{t("chunkPreview.strategy_a")}</Label>
          <Select value={strategyA} onValueChange={setStrategyA}>
            <SelectTrigger aria-label={t("chunkPreview.strategy_a")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {(strategies ?? []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-1.5">
          <Label>{t("chunkPreview.strategy_b")}</Label>
          <Select value={strategyB} onValueChange={setStrategyB}>
            <SelectTrigger aria-label={t("chunkPreview.strategy_b")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={NONE}>{t("chunkPreview.compare_none")}</SelectItem>
              {(strategies ?? [])
                .filter((s) => s.id !== strategyA)
                .map((s) => (
                  <SelectItem key={s.id} value={s.id}>
                    {s.label}
                  </SelectItem>
                ))}
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label htmlFor="chunk-preview-content">{t("chunkPreview.content_label")}</Label>
        <Textarea
          id="chunk-preview-content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          placeholder={t("chunkPreview.content_placeholder")}
          className="min-h-[160px] font-mono text-xs"
        />
      </div>

      {!isComparing && (
        <label className="flex items-center gap-2 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={runPrompts}
            onChange={(e) => setRunPrompts(e.target.checked)}
          />
          {t("chunkPreview.run_prompts")}
        </label>
      )}

      <Button onClick={handleRun} disabled={!canRun}>
        {isPending ? t("chunkPreview.running") : t("chunkPreview.run")}
      </Button>

      {preview.data && preview.data.prompts.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-600">
          <span className="font-semibold">{t("chunkPreview.prompts_title")} :</span>
          {preview.data.prompts.map((p) => (
            <Badge key={p.template_id} variant={p.enabled ? "secondary" : "outline"}>
              {p.template_name} · {p.target}
              {!p.enabled ? ` (${t("chunkPreview.prompt_disabled")})` : ""}
            </Badge>
          ))}
          {preview.data.prompts_executed && (
            <span className="text-emerald-700">✓ {t("chunkPreview.prompts_executed")}</span>
          )}
        </div>
      )}

      {error !== null && (
        <p className="text-sm text-red-600">{t("chunkPreview.error", { message: errorMessage })}</p>
      )}

      {preview.data && (
        <PreviewColumn
          result={preview.data}
          missingHashes={new Set()}
          strategiesById={strategiesById}
        />
      )}

      {compare.data && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            {t("chunkPreview.diff_summary", {
              common: compare.data.diff.common,
              onlyA: compare.data.diff.only_a.length,
              onlyB: compare.data.diff.only_b.length,
            })}
          </p>
          <div className="flex gap-4">
            <PreviewColumn
              result={compare.data.a}
              missingHashes={new Set(compare.data.diff.only_a)}
              strategiesById={strategiesById}
            />
            <PreviewColumn
              result={compare.data.b}
              missingHashes={new Set(compare.data.diff.only_b)}
              strategiesById={strategiesById}
            />
          </div>
        </div>
      )}

      {!preview.data && !compare.data && error === null && (
        <p className="text-sm text-slate-400">{t("chunkPreview.empty_hint")}</p>
      )}
    </div>
  );
}
