import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, HelpCircle, Info } from "lucide-react";
import { HybridSearchHelp } from "@/pages/workspace/HybridSearchHelp";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useToast } from "@/hooks/useToast";
import { useHybridConfig, useSaveHybridConfig } from "@/hooks/useSearchConfig";
import { ApiError } from "@/lib/api";
import { DEFAULT_HYBRID_SPEC, isLexicalEngineUnavailable } from "@/lib/search-config";
import type {
  HybridSpec,
  LexicalEngine,
  LexicalEngineUnavailableDetail,
} from "@/lib/search-config.types";

const LEXICAL_ENGINES: LexicalEngine[] = ["fts", "bm25"];

const asPercent = (value: number) => `${Math.round(value * 100)} %`;

interface Props {
  name: string;
  enabled: boolean;
}

export function WorkspaceSearchTab({ name, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data, isLoading } = useHybridConfig(name, enabled);
  const save = useSaveHybridConfig(name);

  const [form, setForm] = useState<HybridSpec | null>(null);
  const [engineError, setEngineError] = useState<LexicalEngineUnavailableDetail | null>(null);
  const [rebuildJobId, setRebuildJobId] = useState<string | null>(null);

  useEffect(() => {
    if (data) {
      setForm({
        enabled: data.enabled,
        rrf_k: data.rrf_k,
        weight_lexical: data.weight_lexical,
        weight_vector: data.weight_vector,
        lexical_engine: data.lexical_engine,
      });
    }
  }, [data]);

  const submit = (payload: HybridSpec) => {
    setEngineError(null);
    setRebuildJobId(null);
    save.mutate(payload, {
      onSuccess: (config) => {
        setRebuildJobId(config.rebuild_job_id);
        toast({ title: t("search.save.success") });
      },
      onError: (err) => {
        if (err instanceof ApiError && err.status === 422 && isLexicalEngineUnavailable(err.body)) {
          setEngineError(err.body.detail);
          return;
        }
        toast({ title: t("search.save.error"), variant: "destructive" });
      },
    });
  };

  if (isLoading || data === undefined) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  if (data === null || form === null) {
    return (
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-900">{t("search.title")}</h3>
        <HybridSearchHelp />
        <div className="rounded-md border bg-white p-4 space-y-3">
          <p className="text-sm font-medium text-slate-700">{t("search.empty.title")}</p>
          <p className="text-sm text-slate-500">{t("search.empty.description")}</p>
          <Button onClick={() => submit(DEFAULT_HYBRID_SPEC)} disabled={save.isPending}>
            {t("search.empty.activate")}
          </Button>
        </div>
      </div>
    );
  }

  const patch = (partial: Partial<HybridSpec>) => setForm({ ...form, ...partial });

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900">{t("search.title")}</h3>
        <p className="mt-1 text-sm text-slate-600">{t("search.description")}</p>
      </div>

      <HybridSearchHelp />

      {rebuildJobId && (
        <div className="rounded-md border border-sky-200 bg-sky-50 px-4 py-3 flex gap-2 text-sm">
          <Info className="h-4 w-4 text-sky-600 mt-0.5 flex-shrink-0" />
          <p className="text-sky-900">{t("search.save.rebuild", { jobId: rebuildJobId })}</p>
        </div>
      )}

      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit(form);
        }}
        className="space-y-5 rounded-md border bg-white p-4"
      >
        {/* enabled */}
        <div className="flex items-center justify-between">
          <label htmlFor="hybrid-enabled" className="text-sm font-medium text-slate-700">
            {t("search.fields.enabled")}
          </label>
          <Switch
            id="hybrid-enabled"
            checked={form.enabled}
            onCheckedChange={(checked) => patch({ enabled: checked })}
            aria-label={t("search.fields.enabled")}
          />
        </div>

        {/* moteur lexical */}
        <fieldset>
          <legend className="text-sm font-medium text-slate-700">
            {t("search.fields.engine")}
          </legend>
          <div className="mt-2 space-y-2">
            {LEXICAL_ENGINES.map((engine) => (
              <label key={engine} className="flex items-start gap-2 text-sm cursor-pointer">
                <input
                  type="radio"
                  name="lexical-engine"
                  value={engine}
                  checked={form.lexical_engine === engine}
                  onChange={() => patch({ lexical_engine: engine })}
                  className="mt-0.5"
                />
                <span>
                  <span className="font-medium text-slate-800">
                    {t(`search.fields.engines.${engine}`)}
                  </span>
                  <span className="block text-xs text-slate-500">
                    {t(`search.fields.engines.${engine}Help`)}
                  </span>
                </span>
              </label>
            ))}
          </div>
        </fieldset>

        {engineError && (
          <div className="rounded-md border border-rose-200 bg-rose-50 px-4 py-3 flex gap-2 text-sm">
            <AlertCircle className="h-4 w-4 text-rose-600 mt-0.5 flex-shrink-0" />
            <div className="text-rose-900 space-y-1">
              <p className="font-medium">
                {t("search.errors.engineUnavailable", { engine: engineError.engine })}
              </p>
              <p>{engineError.hint}</p>
              <p>{t("search.errors.engineUnavailableExplain")}</p>
            </div>
          </div>
        )}

        {/* poids vectoriel */}
        <div>
          <label htmlFor="weight-vector" className="text-sm font-medium text-slate-700">
            {t("search.fields.weightVector")}
            <span className="ml-2 font-mono text-xs text-slate-500">
              {asPercent(form.weight_vector)}
            </span>
          </label>
          <input
            id="weight-vector"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={form.weight_vector}
            onChange={(e) => patch({ weight_vector: Number(e.target.value) })}
            className="mt-1 block w-full max-w-md"
            aria-label={t("search.fields.weightVector")}
          />
        </div>

        {/* poids lexical */}
        <div>
          <label htmlFor="weight-lexical" className="text-sm font-medium text-slate-700">
            {t("search.fields.weightLexical")}
            <span className="ml-2 font-mono text-xs text-slate-500">
              {asPercent(form.weight_lexical)}
            </span>
          </label>
          <input
            id="weight-lexical"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={form.weight_lexical}
            onChange={(e) => patch({ weight_lexical: Number(e.target.value) })}
            className="mt-1 block w-full max-w-md"
            aria-label={t("search.fields.weightLexical")}
          />
        </div>

        {/* rrf_k (avancé) */}
        <div>
          <label
            htmlFor="rrf-k"
            className="text-sm font-medium text-slate-700 inline-flex items-center gap-1"
          >
            {t("search.fields.rrfK")}
            <TooltipProvider>
              <Tooltip>
                <TooltipTrigger asChild>
                  <span
                    role="img"
                    aria-label={t("search.fields.rrfKHelp")}
                    className="inline-flex cursor-help text-slate-400"
                  >
                    <HelpCircle className="h-3.5 w-3.5" />
                  </span>
                </TooltipTrigger>
                <TooltipContent className="max-w-xs">{t("search.fields.rrfKHelp")}</TooltipContent>
              </Tooltip>
            </TooltipProvider>
          </label>
          <Input
            id="rrf-k"
            type="number"
            min={1}
            value={form.rrf_k}
            onChange={(e) => patch({ rrf_k: Number(e.target.value) })}
            className="mt-1 w-32"
          />
        </div>

        <div className="flex justify-end pt-2">
          <Button type="submit" disabled={save.isPending}>
            {t("search.actions.save")}
          </Button>
        </div>
      </form>
    </div>
  );
}
