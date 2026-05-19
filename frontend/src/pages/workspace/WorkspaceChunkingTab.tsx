import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useToast } from "@/hooks/useToast";
import { useChunkingConfig, useUpsertChunkingConfig } from "@/hooks/useChunking";
import { ApiError } from "@/lib/api";
import { isChunkingChangeRequiresReindex } from "@/lib/chunking";
import type { UpsertChunkingResult } from "@/lib/chunking";
import type { ChunkingSpec, ChunkingStrategy } from "@/lib/chunking.types";
import type { Workspace } from "@/lib/workspaces.types";
import { ChunkingConfirmReindexAlert } from "./ChunkingConfirmReindexAlert";
import {
  CHUNKING_STRATEGIES,
  chunkingFormSchema,
  DEFAULT_CHUNKING_FORM,
  type ChunkingFormValues,
} from "./WorkspaceChunkingTab.schema";

function relativeTimeRaw(iso: string): { key: string; count: number } {
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return { key: "time.justNow", count: 0 };
  if (m < 60) return { key: "time.minutesAgo", count: m };
  const h = Math.floor(m / 60);
  if (h < 24) return { key: "time.hoursAgo", count: h };
  return { key: "time.daysAgo", count: Math.floor(h / 24) };
}

interface Props {
  workspace: Workspace;
  enabled: boolean;
}

export function WorkspaceChunkingTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data, isLoading } = useChunkingConfig(workspace.name, enabled);
  const upsert = useUpsertChunkingConfig(workspace.name);
  const [confirmReindex, setConfirmReindex] = useState<{
    payload: ChunkingSpec;
    current: string;
    next: string;
  } | null>(null);

  const form = useForm<ChunkingFormValues>({
    resolver: zodResolver(chunkingFormSchema),
    defaultValues: DEFAULT_CHUNKING_FORM,
  });

  useEffect(() => {
    if (data) {
      form.reset({
        strategy: data.strategy,
        max_chars: data.max_chars,
        min_chars: data.min_chars,
        overlap_chars: data.overlap_chars,
      });
    }
  }, [data, form]);

  const handleUpsertResult = (result: UpsertChunkingResult) => {
    if (result.status === "no_change") {
      toast({ title: t("chunking.save.noChange") });
    } else if (result.status === "updated") {
      toast({ title: t("chunking.save.success") });
      form.reset({
        strategy: result.config.strategy,
        max_chars: result.config.max_chars,
        min_chars: result.config.min_chars,
        overlap_chars: result.config.overlap_chars,
      });
    } else {
      toast({ title: t("chunking.reindex.triggered") });
      form.reset(form.getValues());
    }
  };

  const onSubmit = (values: ChunkingFormValues) => {
    const payload: ChunkingSpec = { ...values, extras: {} };
    upsert.mutate(
      { payload, confirm: false },
      {
        onSuccess: handleUpsertResult,
        onError: (err) => {
          if (
            err instanceof ApiError &&
            err.status === 409 &&
            isChunkingChangeRequiresReindex(err.body)
          ) {
            setConfirmReindex({
              payload,
              current: err.body.current,
              next: err.body.new,
            });
            return;
          }
          toast({ title: t("chunking.save.error"), variant: "destructive" });
        },
      },
    );
  };

  const onConfirmReindex = () => {
    if (!confirmReindex) return;
    upsert.mutate(
      { payload: confirmReindex.payload, confirm: true },
      {
        onSuccess: (result) => {
          setConfirmReindex(null);
          handleUpsertResult(result);
        },
        onError: () => {
          setConfirmReindex(null);
          toast({ title: t("chunking.save.error"), variant: "destructive" });
        },
      },
    );
  };

  if (isLoading || !data) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          {t("chunking.title")}
          <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-slate-600">
            <span className="h-2 w-2 rounded-full bg-slate-400" />
            {t("chunking.badgeMandatory")}
          </span>
        </h3>
        <p className="mt-1 text-sm text-slate-600">{t("chunking.description")}</p>
      </div>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4 rounded-md border bg-white p-4"
      >
        {/* Stratégie */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.strategy")}
          </label>
          <Controller
            name="strategy"
            control={form.control}
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(v) => field.onChange(v as ChunkingStrategy)}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {CHUNKING_STRATEGIES.map((s) => (
                    <SelectItem key={s} value={s}>
                      {t(`chunking.fields.strategies.${s}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <p className="mt-1 text-xs text-slate-500">
            {t(`chunking.fields.strategyHelp.${form.watch("strategy")}`)}
          </p>
        </div>

        {/* max_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.maxChars")}
          </label>
          <Input
            type="number"
            min={1}
            {...form.register("max_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.maxCharsHelp")}
          </p>
          {form.formState.errors.max_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.max_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        {/* min_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.minChars")}
          </label>
          <Input
            type="number"
            min={0}
            {...form.register("min_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.minCharsHelp")}
          </p>
          {form.formState.errors.min_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.min_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        {/* overlap_chars */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("chunking.fields.overlapChars")}
          </label>
          <Input
            type="number"
            min={0}
            {...form.register("overlap_chars", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          <p className="mt-1 text-xs text-slate-500">
            {t("chunking.fields.overlapCharsHelp")}
          </p>
          {form.formState.errors.overlap_chars && (
            <p className="mt-1 text-xs text-red-600">
              {t(
                `chunking.errors.${form.formState.errors.overlap_chars.message ?? "required"}`,
              )}
            </p>
          )}
        </div>

        <p className="text-xs text-slate-500">
          {(() => {
            const rt = relativeTimeRaw(data.updated_at);
            const when =
              rt.key === "time.justNow"
                ? t("time.justNow")
                : t(rt.key, { count: rt.count });
            return t("chunking.lastModified", { when });
          })()}
        </p>

        <div className="flex items-center justify-end gap-2 pt-2">
          <Button
            type="button"
            variant="ghost"
            onClick={() =>
              form.reset({
                strategy: data.strategy,
                max_chars: data.max_chars,
                min_chars: data.min_chars,
                overlap_chars: data.overlap_chars,
              })
            }
            disabled={!form.formState.isDirty}
          >
            {t("chunking.actions.cancel")}
          </Button>
          <Button
            type="submit"
            disabled={!form.formState.isDirty || upsert.isPending}
          >
            {t("chunking.actions.save")}
          </Button>
        </div>
      </form>

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("chunking.warning")}</p>
      </div>

      {confirmReindex && (
        <ChunkingConfirmReindexAlert
          open={true}
          onOpenChange={(o) => {
            if (!o) setConfirmReindex(null);
          }}
          current={confirmReindex.current}
          next={confirmReindex.next}
          onConfirm={onConfirmReindex}
          pending={upsert.isPending}
        />
      )}
    </div>
  );
}
