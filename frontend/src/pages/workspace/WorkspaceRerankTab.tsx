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
import { useRerankConfig, useUpsertRerankConfig } from "@/hooks/useRerank";
import { DeleteRerankAlert } from "./DeleteRerankAlert";
import type { Workspace } from "@/lib/workspaces.types";
import type { RerankProvider } from "@/lib/rerank.types";
import {
  RERANK_PROVIDERS,
  rerankFormSchema,
  EMPTY_RERANK_FORM,
  type RerankFormValues,
} from "./WorkspaceRerankTab.schema";

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

export function WorkspaceRerankTab({ workspace, enabled }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data, isLoading } = useRerankConfig(workspace.name, enabled);
  const upsert = useUpsertRerankConfig(workspace.name);
  const [deleteOpen, setDeleteOpen] = useState(false);

  const form = useForm<RerankFormValues>({
    resolver: zodResolver(rerankFormSchema),
    defaultValues: EMPTY_RERANK_FORM,
  });

  useEffect(() => {
    if (isLoading) return;
    if (data) {
      form.reset({
        provider: data.provider,
        model: data.model,
        api_key_ref: data.api_key_ref,
        base_url: data.base_url,
        top_k_pre_rerank: data.top_k_pre_rerank,
      });
    } else {
      form.reset(EMPTY_RERANK_FORM);
    }
  }, [data, isLoading, form]);

  const provider = form.watch("provider");
  const apiKeyApplicable = provider === "cohere" || provider === "voyage";
  const baseUrlApplicable = provider === "ollama";

  const onSubmit = (values: RerankFormValues) => {
    const payload = {
      provider: values.provider,
      model: values.model,
      api_key_ref: apiKeyApplicable ? values.api_key_ref : null,
      base_url: baseUrlApplicable ? values.base_url : null,
      top_k_pre_rerank: values.top_k_pre_rerank,
    };
    upsert.mutate(payload, {
      onSuccess: (saved) => {
        toast({ title: t("rerank.save.success") });
        form.reset({
          provider: saved.provider,
          model: saved.model,
          api_key_ref: saved.api_key_ref,
          base_url: saved.base_url,
          top_k_pre_rerank: saved.top_k_pre_rerank,
        });
      },
      onError: () => toast({ title: t("rerank.save.error"), variant: "destructive" }),
    });
  };

  if (isLoading) {
    return (
      <div className="flex h-32 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  const configured = data !== null && data !== undefined;

  return (
    <div className="space-y-4">
      <div>
        <h3 className="text-sm font-semibold text-slate-900 flex items-center gap-2">
          {configured ? t("rerank.title") : t("rerank.titleOptional")}
          {configured && (
            <span className="ml-auto inline-flex items-center gap-1 text-xs font-medium text-emerald-700">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              {t("rerank.badge.active")}
            </span>
          )}
        </h3>
        <p className="mt-1 text-sm text-slate-600">
          {configured ? t("rerank.description.configured") : t("rerank.description.empty")}
        </p>
      </div>

      <form
        onSubmit={form.handleSubmit(onSubmit)}
        className="space-y-4 rounded-md border bg-white p-4"
      >
        {/* Provider */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.provider")}
          </label>
          <Controller
            name="provider"
            control={form.control}
            render={({ field }) => (
              <Select
                value={field.value}
                onValueChange={(v) => field.onChange(v as RerankProvider)}
              >
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("rerank.fields.providerPlaceholder")} />
                </SelectTrigger>
                <SelectContent>
                  {RERANK_PROVIDERS.map((p) => (
                    <SelectItem key={p} value={p}>
                      {t(`rerank.fields.providers.${p}`)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
        </div>

        {/* Modèle */}
        <div>
          <label className="text-sm font-medium text-slate-700">{t("rerank.fields.model")}</label>
          <Input
            {...form.register("model")}
            placeholder={t("rerank.fields.modelPlaceholder")}
            className="mt-1 font-mono"
          />
          {form.formState.errors.model && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.model.message ?? "required"}`)}
            </p>
          )}
        </div>

        {/* Base URL */}
        <div>
          <label className="text-sm font-medium text-slate-700">{t("rerank.fields.baseUrl")}</label>
          <Input
            {...form.register("base_url", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
            disabled={!baseUrlApplicable}
            placeholder={
              baseUrlApplicable
                ? t("rerank.fields.baseUrlPlaceholder")
                : t("rerank.fields.baseUrlNotApplicable")
            }
            className="mt-1 font-mono"
          />
          {form.formState.errors.base_url && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.base_url.message ?? "invalid_url"}`)}
            </p>
          )}
        </div>

        {/* API key ref */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.apiKeyRef")}
          </label>
          <Input
            {...form.register("api_key_ref", {
              setValueAs: (v) => (v === "" ? null : v),
            })}
            disabled={!apiKeyApplicable}
            placeholder={
              apiKeyApplicable
                ? t("rerank.fields.apiKeyRefPlaceholder")
                : t("rerank.fields.apiKeyRefNotApplicable")
            }
            className="mt-1 font-mono"
          />
          {form.formState.errors.api_key_ref && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.api_key_ref.message ?? "required"}`)}
            </p>
          )}
        </div>

        {/* top_k pre-rerank */}
        <div>
          <label className="text-sm font-medium text-slate-700">
            {t("rerank.fields.topK")}{" "}
            <span className="text-slate-500 font-normal">{t("rerank.fields.topKHelp")}</span>
          </label>
          <Input
            type="number"
            min={1}
            max={500}
            {...form.register("top_k_pre_rerank", { valueAsNumber: true })}
            className="mt-1 w-32"
          />
          {form.formState.errors.top_k_pre_rerank && (
            <p className="mt-1 text-xs text-red-600">
              {t(`rerank.errors.${form.formState.errors.top_k_pre_rerank.message ?? "required"}`)}
            </p>
          )}
        </div>

        {configured && data && (
          <p className="text-xs text-slate-500">
            {(() => {
              const rt = relativeTimeRaw(data.updated_at);
              const when =
                rt.key === "time.justNow" ? t("time.justNow") : t(rt.key, { count: rt.count });
              return t("rerank.lastModified", { when });
            })()}
          </p>
        )}

        <div className="flex items-center justify-between pt-2">
          <div>
            {configured && (
              <Button
                type="button"
                variant="outline"
                className="text-red-600 border-red-200 hover:bg-red-50"
                onClick={() => setDeleteOpen(true)}
              >
                {t("rerank.actions.delete")}
              </Button>
            )}
          </div>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="ghost"
              onClick={() => form.reset(data ?? EMPTY_RERANK_FORM)}
              disabled={!form.formState.isDirty}
            >
              {t("rerank.actions.cancel")}
            </Button>
            <Button type="submit" disabled={!form.formState.isDirty || upsert.isPending}>
              {configured ? t("rerank.actions.save") : t("rerank.actions.activate")}
            </Button>
          </div>
        </div>
      </form>

      <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 flex gap-2 text-sm">
        <AlertTriangle className="h-4 w-4 text-amber-600 mt-0.5 flex-shrink-0" />
        <p className="text-amber-900">{t("rerank.warning")}</p>
      </div>

      <DeleteRerankAlert name={workspace.name} open={deleteOpen} onOpenChange={setDeleteOpen} />
    </div>
  );
}
