import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useChunkingStrategies } from "@/hooks/useChunkingStrategies";
import { useSetDefaultStrategy } from "@/hooks/useChunking";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { isChunkingChangeRequiresReindex, type SetDefaultStrategyResult } from "@/lib/chunking";
import { ChunkingConfirmReindexAlert } from "./ChunkingConfirmReindexAlert";

const CASCADE = "__cascade__"; // pas de binding — cascade textuelle par catégories

interface Props {
  workspaceName: string;
  defaultStrategyId: string | null;
}

export function DefaultStrategyPanel({ workspaceName, defaultStrategyId }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const { data: strategies } = useChunkingStrategies();
  const mutation = useSetDefaultStrategy(workspaceName);

  const [selected, setSelected] = useState<string>(defaultStrategyId ?? CASCADE);
  const [confirmReindex, setConfirmReindex] = useState<{ current: string; next: string } | null>(
    null,
  );

  useEffect(() => {
    setSelected(defaultStrategyId ?? CASCADE);
  }, [defaultStrategyId]);

  const strategyId = selected === CASCADE ? null : selected;
  const dirty = strategyId !== defaultStrategyId;

  const handleResult = (result: SetDefaultStrategyResult) => {
    if (result.status === "reindex_triggered") {
      toast({ title: t("chunking.reindex.triggered") });
    } else {
      toast({ title: t("chunking.defaultStrategy.saved") });
    }
  };

  const save = (confirm: boolean) => {
    mutation.mutate(
      { strategyId, confirm },
      {
        onSuccess: (result) => {
          setConfirmReindex(null);
          handleResult(result);
        },
        onError: (err) => {
          if (
            err instanceof ApiError &&
            err.status === 409 &&
            isChunkingChangeRequiresReindex(err.body)
          ) {
            setConfirmReindex({ current: err.body.current, next: err.body.new });
            return;
          }
          toast({ title: t("chunking.defaultStrategy.error"), variant: "destructive" });
        },
      },
    );
  };

  return (
    <div className="rounded-md border border-slate-200 p-4 space-y-3">
      <div>
        <h4 className="text-sm font-semibold text-slate-900">
          {t("chunking.defaultStrategy.title")}
        </h4>
        <p className="mt-1 text-sm text-slate-600">{t("chunking.defaultStrategy.description")}</p>
      </div>
      <div className="flex items-end gap-3">
        <div className="flex-1 space-y-1.5">
          <Label>{t("chunking.defaultStrategy.label")}</Label>
          <Select value={selected} onValueChange={setSelected}>
            <SelectTrigger aria-label={t("chunking.defaultStrategy.label")}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value={CASCADE}>{t("chunking.defaultStrategy.cascade")}</SelectItem>
              {(strategies ?? []).map((s) => (
                <SelectItem key={s.id} value={s.id}>
                  {s.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <Button onClick={() => save(false)} disabled={!dirty || mutation.isPending}>
          {t("chunking.defaultStrategy.save")}
        </Button>
      </div>

      <ChunkingConfirmReindexAlert
        open={confirmReindex !== null}
        onOpenChange={(open) => {
          if (!open) setConfirmReindex(null);
        }}
        current={confirmReindex?.current ?? ""}
        next={confirmReindex?.next ?? ""}
        onConfirm={() => save(true)}
        pending={mutation.isPending}
      />
    </div>
  );
}
