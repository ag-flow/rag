import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, Trash2 } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import {
  useChunkingStrategies,
  useSetStrategyRoutes,
  useStrategyDetail,
} from "@/hooks/useChunkingStrategies";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import {
  OVERFLOW_POLICIES,
  REGION_TYPES,
  type OverflowPolicy,
  type RegionRouteSpec,
  type RegionType,
  type StrategyOut,
} from "@/lib/chunking-strategies.types";

const INLINE = "__inline__";

// Info-strings de fences les plus courants — suggestions, pas une liste fermée
// (le qualifier reste libre : n'importe quel info-string peut être routé).
const QUALIFIER_SUGGESTIONS = [
  "*",
  "mermaid",
  "python",
  "typescript",
  "javascript",
  "csharp",
  "go",
  "java",
  "sql",
  "bash",
  "json",
  "yaml",
  "xml",
] as const;

interface Props {
  strategy: StrategyOut;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

function newRoute(): RegionRouteSpec {
  return {
    region_type: "code_fence",
    qualifier: "*",
    target_strategy_id: null,
    atomic: true,
    overflow_policy: "keep_whole",
  };
}

export function RoutesEditorDialog({ strategy, open, onOpenChange }: Props) {
  const { t } = useTranslation("chunking_strategies");
  const { toast } = useToast();
  const detail = useStrategyDetail(open ? strategy.id : null);
  const { data: allStrategies } = useChunkingStrategies(open);
  const save = useSetStrategyRoutes();
  const [routes, setRoutes] = useState<RegionRouteSpec[]>([]);

  useEffect(() => {
    if (detail.data) setRoutes(detail.data.routes);
  }, [detail.data]);

  const targets = (allStrategies ?? []).filter((s) => s.id !== strategy.id);
  const keys = routes.map((r) => `${r.region_type}:${r.qualifier}`);
  const hasDuplicate = new Set(keys).size !== keys.length;

  function update(index: number, patch: Partial<RegionRouteSpec>) {
    setRoutes(routes.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }

  async function handleSave() {
    try {
      await save.mutateAsync({ id: strategy.id, routes });
      toast({ title: t("toasts.routes_saved") });
      onOpenChange(false);
    } catch (err) {
      const label =
        err instanceof ApiError && err.status === 422 ? t("errors.invalid") : t("errors.generic");
      toast({ title: label, variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[820px]">
        <DialogHeader>
          <DialogTitle>{t("routes.title", { label: strategy.label })}</DialogTitle>
        </DialogHeader>
        <p className="text-sm text-slate-500">{t("routes.subtitle")}</p>

        {detail.isLoading ? (
          <LoadingSpinner />
        ) : (
          <div className="space-y-2">
            {routes.length === 0 && <p className="text-sm text-slate-500">{t("routes.empty")}</p>}
            {routes.map((route, i) => (
              <div
                key={i}
                className="grid grid-cols-[1fr_1fr_1.4fr_auto_1.4fr_auto] items-center gap-2 rounded-md border border-slate-200 p-2"
              >
                <Select
                  value={route.region_type}
                  onValueChange={(v) => update(i, { region_type: v as RegionType })}
                >
                  <SelectTrigger aria-label={t("routes.region_type")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {REGION_TYPES.map((rt) => (
                      <SelectItem key={rt} value={rt}>
                        {rt}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Input
                  value={route.qualifier}
                  onChange={(e) => update(i, { qualifier: e.target.value })}
                  placeholder={t("routes.qualifier_hint")}
                  aria-label={t("routes.qualifier")}
                  list="route-qualifier-suggestions"
                />
                <Select
                  value={route.target_strategy_id ?? INLINE}
                  onValueChange={(v) => update(i, { target_strategy_id: v === INLINE ? null : v })}
                >
                  <SelectTrigger aria-label={t("routes.target")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={INLINE}>{t("routes.target_inline")}</SelectItem>
                    {targets.map((s) => (
                      <SelectItem key={s.id} value={s.id}>
                        {s.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <label className="flex items-center gap-1.5 text-xs text-slate-600">
                  <Switch
                    checked={route.atomic}
                    onCheckedChange={(v) => update(i, { atomic: v })}
                    aria-label={t("routes.atomic")}
                  />
                  {t("routes.atomic")}
                </label>
                <Select
                  value={route.overflow_policy}
                  onValueChange={(v) => update(i, { overflow_policy: v as OverflowPolicy })}
                >
                  <SelectTrigger aria-label={t("routes.policy")}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {OVERFLOW_POLICIES.map((p) => (
                      <SelectItem key={p} value={p}>
                        {t(`routes.policies.${p}`)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Button
                  variant="ghost"
                  size="icon"
                  onClick={() => setRoutes(routes.filter((_, j) => j !== i))}
                  aria-label={t("routes.remove")}
                >
                  <Trash2 className="h-4 w-4 text-red-600" />
                </Button>
              </div>
            ))}
            {hasDuplicate && <p className="text-sm text-red-600">{t("routes.duplicate_key")}</p>}
            <Button variant="outline" size="sm" onClick={() => setRoutes([...routes, newRoute()])}>
              <Plus className="mr-1 h-4 w-4" />
              {t("routes.add")}
            </Button>
          </div>
        )}

        <datalist id="route-qualifier-suggestions">
          {QUALIFIER_SUGGESTIONS.map((q) => (
            <option key={q} value={q} />
          ))}
        </datalist>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            {t("form.cancel")}
          </Button>
          <Button
            onClick={() => void handleSave()}
            disabled={hasDuplicate || save.isPending || detail.isLoading}
          >
            {t("routes.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
