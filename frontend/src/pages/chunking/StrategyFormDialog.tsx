import { useEffect, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { HelpCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/tooltip";
import { Plus, Trash2 } from "lucide-react";
import {
  useChunkingParsers,
  useCreateStrategy,
  usePatchStrategy,
  useSetStrategyPrompts,
  useStrategyDetail,
} from "@/hooks/useChunkingStrategies";
import { usePrompts } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { AlgoInfoPanel } from "@/pages/chunking/AlgoInfoPanel";
import { AddPromptDialog } from "@/pages/workspace/AddPromptDialog";
import {
  CHUNKING_ALGOS,
  type ChunkingAlgo,
  type StrategyOut,
} from "@/lib/chunking-strategies.types";

const NUMERIC_PARAMS = ["child_target_tokens", "floor_tokens", "overlap_tokens"] as const;
const CLEANING_PARAMS = [
  "clean_content",
  "strip_separators",
  "strip_boilerplate",
  "strip_html",
] as const;
const PARSER_ALGOS: ChunkingAlgo[] = ["prose", "markdown"];
const NONE = "__none__";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  strategy: StrategyOut | null; // null = création
}

function numericDefaults(strategy: StrategyOut | null): Record<string, string> {
  const out: Record<string, string> = {};
  for (const key of [...NUMERIC_PARAMS, "breadcrumb_depth", "max_rows_per_chunk"]) {
    const v = strategy?.params[key];
    out[key] = typeof v === "number" ? String(v) : "";
  }
  return out;
}

function cleaningDefaults(strategy: StrategyOut | null): Record<string, boolean> {
  const out: Record<string, boolean> = {};
  for (const key of CLEANING_PARAMS) out[key] = strategy?.params[key] === true;
  return out;
}

export function StrategyFormDialog({ open, onOpenChange, strategy }: Props) {
  const { t } = useTranslation("chunking_strategies");
  const { toast } = useToast();
  const { data: parsers } = useChunkingParsers(open);
  const create = useCreateStrategy();
  const patch = usePatchStrategy();
  const setPromptsMutation = useSetStrategyPrompts();
  const { data: allTemplates = [] } = usePrompts();
  const detail = useStrategyDetail(open && strategy !== null ? strategy.id : null);

  const [label, setLabel] = useState("");
  const [algo, setAlgo] = useState<ChunkingAlgo>("prose");
  const [parserSlug, setParserSlug] = useState<string>(NONE);
  const [numbers, setNumbers] = useState<Record<string, string>>({});
  const [headingLevels, setHeadingLevels] = useState("");
  const [cleaning, setCleaning] = useState<Record<string, boolean>>({});
  // Bindings de prompts inline (S6.4) : ordre = position dans la liste.
  const [prompts, setPrompts] = useState<{ template_id: string; enabled: boolean }[]>([]);
  // Création de template sans quitter la stratégie, pré-réglée sur le mode
  // chunk (seuls chunk/région sont liables ici).
  const [promptDialogOpen, setPromptDialogOpen] = useState(false);

  useEffect(() => {
    if (!open) return;
    setLabel(strategy?.label ?? "");
    setAlgo(strategy?.algo ?? "prose");
    setParserSlug(strategy?.parser_slug ?? NONE);
    setNumbers(numericDefaults(strategy));
    const levels = strategy?.params["heading_levels"];
    setHeadingLevels(Array.isArray(levels) ? levels.join(",") : "");
    setCleaning(cleaningDefaults(strategy));
    setPrompts([]);
  }, [open, strategy]);

  useEffect(() => {
    if (detail.data) {
      setPrompts(
        detail.data.prompts.map((p) => ({ template_id: p.template_id, enabled: p.enabled })),
      );
    }
  }, [detail.data]);

  const isEdit = strategy !== null;
  const parserAllowed = PARSER_ALGOS.includes(algo);
  const isPending = create.isPending || patch.isPending;
  const usage =
    strategy !== null
      ? strategy.used_by_routes +
        strategy.used_by_categories +
        strategy.used_by_triggers +
        strategy.used_by_workspaces
      : 0;

  function buildParams(): Record<string, unknown> {
    const params: Record<string, unknown> = {};
    for (const key of NUMERIC_PARAMS) {
      if (numbers[key]) params[key] = Number(numbers[key]);
    }
    if (numbers["breadcrumb_depth"])
      params["breadcrumb_depth"] = Number(numbers["breadcrumb_depth"]);
    if (algo === "table" && numbers["max_rows_per_chunk"]) {
      params["max_rows_per_chunk"] = Number(numbers["max_rows_per_chunk"]);
    }
    if (PARSER_ALGOS.includes(algo) && headingLevels.trim()) {
      const levels = headingLevels
        .split(",")
        .map((v) => Number(v.trim()))
        .filter((n) => Number.isInteger(n) && n >= 1 && n <= 6);
      if (levels.length > 0) params["heading_levels"] = levels;
    }
    for (const key of CLEANING_PARAMS) {
      if (cleaning[key]) params[key] = true;
    }
    return params;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!label.trim() || isPending) return;
    const parser = parserAllowed && parserSlug !== NONE ? parserSlug : null;
    try {
      let strategyId: string;
      if (isEdit) {
        const updated = await patch.mutateAsync({
          id: strategy.id,
          payload: { label: label.trim(), params: buildParams(), parser_slug: parser },
        });
        strategyId = updated.id;
        toast({ title: t("toasts.updated") });
      } else {
        const created = await create.mutateAsync({
          label: label.trim(),
          algo,
          params: buildParams(),
          parser_slug: parser,
        });
        strategyId = created.id;
        toast({ title: t("toasts.created") });
      }
      await setPromptsMutation.mutateAsync({
        id: strategyId,
        prompts: prompts.map((p, i) => ({
          template_id: p.template_id,
          order_index: i + 1,
          enabled: p.enabled,
        })),
      });
      onOpenChange(false);
    } catch (err) {
      toast({ title: errorLabel(err, t), variant: "destructive" });
    }
  }

  const parserSelected = parserAllowed && parserSlug !== NONE;
  // Seuls les templates embedding_inline se lient ; region:* exige un parser.
  const bindableTemplates = allTemplates.filter(
    (tpl) =>
      tpl.timing === "embedding_inline" && (parserSelected || !tpl.target.startsWith("region:")),
  );

  const tableAlgo = algo === "table";
  const numericKeys = tableAlgo
    ? (["child_target_tokens", "max_rows_per_chunk"] as const)
    : ([...NUMERIC_PARAMS, "breadcrumb_depth"] as const);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[920px] max-h-[88vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{isEdit ? t("form.edit_title") : t("form.create_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="grid gap-6 md:grid-cols-[1fr_300px]">
          <div className="space-y-4">
            {isEdit && usage > 0 && (
              <p className="rounded-md bg-amber-50 px-3 py-2 text-sm text-amber-800">
                {t("form.linked_warning", {
                  usage: (
                    [
                      ["badges.used_by_routes", strategy.used_by_routes],
                      ["badges.used_by_categories", strategy.used_by_categories],
                      ["badges.used_by_triggers", strategy.used_by_triggers],
                      ["badges.used_by_workspaces", strategy.used_by_workspaces],
                    ] as [string, number][]
                  )
                    .filter(([, count]) => count > 0)
                    .map(([key, count]) => t(key, { count }))
                    .join(" · "),
                })}
              </p>
            )}
            <div className="space-y-1.5">
              <Label htmlFor="strategy-label">{t("form.label")}</Label>
              <Input
                id="strategy-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder={t("form.label_placeholder")}
                maxLength={128}
              />
              <p className="text-xs text-slate-500">
                {isEdit ? `${t("form.slug")} : ${strategy.slug} — ` : ""}
                {t("form.slug_hint")}
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <Label>{t("form.algo")}</Label>
                <Select
                  value={algo}
                  onValueChange={(v) => setAlgo(v as ChunkingAlgo)}
                  disabled={isEdit}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {CHUNKING_ALGOS.map((a) => (
                      <SelectItem key={a} value={a}>
                        {a}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                {isEdit && <p className="text-xs text-slate-500">{t("form.algo_locked")}</p>}
              </div>
              <div className="space-y-1.5">
                <Label>{t("form.parser")}</Label>
                <Select
                  value={parserAllowed ? parserSlug : NONE}
                  onValueChange={setParserSlug}
                  disabled={!parserAllowed}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={NONE}>{t("form.parser_none")}</SelectItem>
                    {(parsers ?? []).map((p) => (
                      <SelectItem key={p.slug} value={p.slug}>
                        {p.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-slate-500">{t("form.parser_hint")}</p>
              </div>
            </div>

            <div className="space-y-2">
              <Label>{t("form.params_title")}</Label>
              <TooltipProvider delayDuration={150}>
                <div className="grid grid-cols-2 gap-3">
                  {numericKeys.map((key) => (
                    <div key={key} className="space-y-1">
                      <span className="flex items-center gap-1">
                        <Label htmlFor={`param-${key}`} className="text-xs font-normal">
                          {t(`form.params.${key}`)}
                        </Label>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              aria-label={t("form.params_help_aria", {
                                param: t(`form.params.${key}`),
                              })}
                              className="text-slate-400 hover:text-slate-600"
                            >
                              <HelpCircle className="h-3.5 w-3.5" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[280px] text-xs">
                            {t(`form.params_help.${key}`)}
                          </TooltipContent>
                        </Tooltip>
                      </span>
                      <Input
                        id={`param-${key}`}
                        type="number"
                        value={numbers[key] ?? ""}
                        onChange={(e) => setNumbers({ ...numbers, [key]: e.target.value })}
                      />
                    </div>
                  ))}
                  {PARSER_ALGOS.includes(algo) && (
                    <div className="space-y-1">
                      <span className="flex items-center gap-1">
                        <Label htmlFor="param-heading-levels" className="text-xs font-normal">
                          {t("form.params.heading_levels")}
                        </Label>
                        <Tooltip>
                          <TooltipTrigger asChild>
                            <button
                              type="button"
                              aria-label={t("form.params_help_aria", {
                                param: t("form.params.heading_levels"),
                              })}
                              className="text-slate-400 hover:text-slate-600"
                            >
                              <HelpCircle className="h-3.5 w-3.5" />
                            </button>
                          </TooltipTrigger>
                          <TooltipContent side="top" className="max-w-[280px] text-xs">
                            {t("form.params_help.heading_levels")}
                          </TooltipContent>
                        </Tooltip>
                      </span>
                      <Input
                        id="param-heading-levels"
                        value={headingLevels}
                        onChange={(e) => setHeadingLevels(e.target.value)}
                        placeholder="1,2"
                      />
                    </div>
                  )}
                </div>
              </TooltipProvider>
            </div>

            <div className="space-y-2">
              <Label>{t("form.cleaning_title")}</Label>
              {CLEANING_PARAMS.map((key) => (
                <div key={key} className="flex items-center justify-between">
                  <span className="text-sm text-slate-700">{t(`form.cleaning.${key}`)}</span>
                  <Switch
                    checked={cleaning[key] ?? false}
                    onCheckedChange={(v) => setCleaning({ ...cleaning, [key]: v })}
                    aria-label={key}
                  />
                </div>
              ))}
            </div>

            <div className="space-y-2">
              <Label>{t("form.prompts_title")}</Label>
              <p className="text-xs text-amber-700">{t("form.prompts_warning")}</p>
              {prompts.map((binding, i) => {
                const tpl = allTemplates.find((x) => x.id === binding.template_id);
                return (
                  <div
                    key={binding.template_id}
                    className="flex items-center gap-2 rounded-md border border-slate-200 px-2 py-1.5"
                  >
                    <span className="flex-1 truncate text-sm text-slate-700">
                      {tpl?.name ?? binding.template_id}
                      <span className="ml-2 text-xs text-slate-400">{tpl?.target}</span>
                    </span>
                    <Switch
                      checked={binding.enabled}
                      onCheckedChange={(v) =>
                        setPrompts(prompts.map((x, j) => (j === i ? { ...x, enabled: v } : x)))
                      }
                      aria-label={t("form.prompts_enabled")}
                    />
                    <Button
                      type="button"
                      variant="ghost"
                      size="icon"
                      onClick={() => setPrompts(prompts.filter((_, j) => j !== i))}
                      aria-label={t("form.prompts_remove")}
                    >
                      <Trash2 className="h-4 w-4 text-red-600" />
                    </Button>
                  </div>
                );
              })}
              {bindableTemplates.filter((tpl) => !prompts.some((p) => p.template_id === tpl.id))
                .length > 0 ? (
                <Select
                  value=""
                  onValueChange={(templateId) =>
                    setPrompts([...prompts, { template_id: templateId, enabled: true }])
                  }
                >
                  <SelectTrigger aria-label={t("form.prompts_add")} className="w-fit gap-1">
                    <Plus className="h-4 w-4" />
                    {t("form.prompts_add")}
                  </SelectTrigger>
                  <SelectContent>
                    {bindableTemplates
                      .filter((tpl) => !prompts.some((p) => p.template_id === tpl.id))
                      .map((tpl) => (
                        <SelectItem key={tpl.id} value={tpl.id}>
                          {tpl.name} — {tpl.target}
                        </SelectItem>
                      ))}
                  </SelectContent>
                </Select>
              ) : (
                prompts.length === 0 && (
                  <p className="text-xs text-slate-400">{t("form.prompts_none")}</p>
                )
              )}
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1"
                onClick={() => setPromptDialogOpen(true)}
              >
                <Plus className="h-4 w-4" />
                {t("form.prompts_create")}
              </Button>
            </div>
          </div>

          <AlgoInfoPanel algo={algo} />

          <DialogFooter className="md:col-span-2">
            <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
              {t("form.cancel")}
            </Button>
            <Button type="submit" disabled={!label.trim() || isPending}>
              {isEdit ? t("form.save") : t("form.create")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
      <AddPromptDialog
        open={promptDialogOpen}
        onOpenChange={setPromptDialogOpen}
        initialMode="chunk"
      />
    </Dialog>
  );
}

function errorLabel(err: unknown, t: (k: string) => string): string {
  if (err instanceof ApiError) {
    if (err.status === 409) return t("errors.conflict");
    if (err.status === 403) return t("errors.system_immutable");
    if (err.status === 422) return t("errors.invalid");
  }
  return t("errors.generic");
}
