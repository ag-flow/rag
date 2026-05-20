import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Eye, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/useToast";
import { useUpdateApiKeyRef } from "@/hooks/useWorkspaces";
import type { Workspace } from "@/lib/workspaces.types";

const schema = z.object({
  api_key_ref: z
    .string()
    .min(1)
    .regex(/^[a-zA-Z0-9_]+$/, "alphanum_underscore_only"),
});

type FormValues = z.infer<typeof schema>;

interface Props {
  workspace: Workspace;
  onReveal: () => void;
  onRotate: () => void;
}

function relativeTimeRaw(iso: string | null): { key: string; count: number } | null {
  if (!iso) return null;
  const diffMs = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diffMs / 60_000);
  if (m < 1) return { key: "time.justNow", count: 0 };
  if (m < 60) return { key: "time.minutesAgo", count: m };
  const h = Math.floor(m / 60);
  if (h < 24) return { key: "time.hoursAgo", count: h };
  return { key: "time.daysAgo", count: Math.floor(h / 24) };
}

export function WorkspaceDetailTab({ workspace, onReveal, onRotate }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const updateRef = useUpdateApiKeyRef(workspace.name);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { api_key_ref: workspace.indexer.api_key_ref ?? "" },
  });

  const onSubmit = (values: FormValues) => {
    updateRef.mutate(
      { indexer: { api_key_ref: values.api_key_ref } },
      {
        onSuccess: () => {
          toast({ title: t("detail.save.success") });
          form.reset({ api_key_ref: values.api_key_ref });
        },
        onError: () => toast({ title: t("detail.save.error"), variant: "destructive" }),
      },
    );
  };

  return (
    <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
      {/* Section 1 : Stats */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.stats.title")}
        </h3>
        <div className="text-sm text-slate-700">
          {t("detail.stats.sources", { count: workspace.sources_count })}
          {" · "}
          {t("detail.stats.documents", { count: workspace.documents_count })}
          {" · "}
          {(() => {
            const rel = relativeTimeRaw(workspace.last_indexed_at);
            const when = !rel
              ? "—"
              : rel.key === "time.justNow"
                ? t("time.justNow")
                : t(rel.key, { count: rel.count });
            return t("detail.stats.lastIndexed", { when });
          })()}
        </div>
      </section>

      {/* Section 2 : API key workspace */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.apikey.title")}
        </h3>
        <div className="flex items-center gap-2">
          <code className="bg-slate-100 px-3 py-1 rounded text-xs font-mono">
            ••••••••••••••••••••••••
          </code>
          <Button type="button" size="sm" variant="outline" onClick={onReveal}>
            <Eye className="h-3.5 w-3.5" /> {t("detail.apikey.reveal")}
          </Button>
          <Button type="button" size="sm" variant="outline" onClick={onRotate}>
            <RefreshCw className="h-3.5 w-3.5" /> {t("detail.apikey.rotate")}
          </Button>
        </div>
      </section>

      {/* Section 3 : api_key_ref éditable */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.apiKeyRef.title")}{" "}
          <span className="text-emerald-600 normal-case">— {t("detail.apiKeyRef.editable")}</span>
        </h3>
        <div className="flex items-center gap-2">
          <Input {...form.register("api_key_ref")} className="font-mono text-sm flex-1" />
          <Button type="submit" size="sm" disabled={!form.formState.isDirty || updateRef.isPending}>
            {t("detail.apiKeyRef.save")}
          </Button>
        </div>
        {form.formState.errors.api_key_ref && (
          <p className="mt-1 text-xs text-red-600">
            {t(`detail.apiKeyRef.errors.${form.formState.errors.api_key_ref.message ?? "invalid"}`)}
          </p>
        )}
      </section>

      {/* Section 4 : Identifiants read-only */}
      <section>
        <h3 className="text-xs font-medium uppercase tracking-wider text-slate-500 mb-2">
          {t("detail.ids.title")}
        </h3>
        <div className="text-sm text-slate-700 space-y-1">
          <div>
            {t("detail.ids.name")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.name}</code>
          </div>
          <div>
            {t("detail.ids.id")}:{" "}
            <code className="bg-slate-100 px-2 py-0.5 rounded text-xs">{workspace.id}</code>
          </div>
        </div>
      </section>
    </form>
  );
}
