import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/button";
import { useSetChunkingEngine } from "@/hooks/useChunking";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { isChunkingChangeRequiresReindex, type SetEngineResult } from "@/lib/chunking";
import type { ChunkingEngine } from "@/lib/chunking.types";
import { ChunkingConfirmReindexAlert } from "./ChunkingConfirmReindexAlert";

interface Props {
  workspaceName: string;
  targetEngine: ChunkingEngine;
  variant?: "default" | "outline" | "ghost";
}

/**
 * Bouton de bascule du moteur de chunking (`legacy` ↔ `structured`).
 * Protocole 409/confirm : premier PUT sans confirm ; si le backend répond
 * `chunking_change_requires_reindex`, ouvre le dialog de réindexation qui
 * relance la mutation avec confirm=true (202 → toast job lancé).
 */
export function ChunkingEngineSwitch({ workspaceName, targetEngine, variant = "default" }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const mutation = useSetChunkingEngine(workspaceName);
  const [confirmReindex, setConfirmReindex] = useState<{ current: string; next: string } | null>(
    null,
  );

  const handleResult = (result: SetEngineResult) => {
    if (result.status === "no_change") {
      toast({ title: t("chunking.save.noChange") });
    } else if (result.status === "updated") {
      toast({ title: t("chunking.engine.switched") });
    } else {
      toast({ title: t("chunking.reindex.triggered") });
    }
  };

  const save = (confirm: boolean) => {
    mutation.mutate(
      { engine: targetEngine, confirm },
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
          setConfirmReindex(null);
          toast({ title: t("chunking.engine.error"), variant: "destructive" });
        },
      },
    );
  };

  const label =
    targetEngine === "structured"
      ? t("chunking.engine.actions.switchToStructured")
      : t("chunking.engine.actions.switchToLegacy");

  return (
    <>
      <Button
        type="button"
        variant={variant}
        size="sm"
        onClick={() => save(false)}
        disabled={mutation.isPending}
      >
        {label}
      </Button>
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
    </>
  );
}
