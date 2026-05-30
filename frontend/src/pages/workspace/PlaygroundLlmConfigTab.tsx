import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useLlmConfigs, useDeleteLlmConfig, usePatchLlmConfig } from "@/hooks/usePlayground";
import { useToast } from "@/hooks/useToast";
import { AddLlmConfigDialog } from "./AddLlmConfigDialog";
import type { LlmConfig } from "@/lib/playground.types";

interface Props {
  workspaceName: string;
}

export function PlaygroundLlmConfigTab({ workspaceName }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const { data: configs = [], isLoading } = useLlmConfigs(workspaceName);
  const deleteMutation = useDeleteLlmConfig(workspaceName);
  const patchMutation = usePatchLlmConfig(workspaceName);
  const [addOpen, setAddOpen] = useState(false);
  const [toDelete, setToDelete] = useState<LlmConfig | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("config.deleted_toast") });
    } catch {
      toast({ title: t("config.error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  async function handleToggle(cfg: LlmConfig) {
    await patchMutation.mutateAsync({ configId: cfg.id, payload: { enabled: !cfg.enabled } });
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("config.add_btn")}
        </Button>
      </div>

      {!isLoading && configs.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("config.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("config.col_provider")}</TableHead>
                <TableHead>{t("config.col_model")}</TableHead>
                <TableHead>{t("config.col_key")}</TableHead>
                <TableHead>{t("config.col_enabled")}</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {configs.map((cfg) => (
                <TableRow key={cfg.id}>
                  <TableCell>
                    <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700">
                      {cfg.provider}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-sm">{cfg.model}</TableCell>
                  <TableCell className="text-xs text-slate-400">
                    {cfg.api_key_ref ? cfg.api_key_ref.split("/").pop() ?? "—" : "—"}
                  </TableCell>
                  <TableCell>
                    <Switch
                      checked={cfg.enabled}
                      onCheckedChange={() => handleToggle(cfg)}
                      disabled={patchMutation.isPending}
                    />
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(cfg)}
                      className="text-rose-600 hover:text-rose-700"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddLlmConfigDialog
        workspaceName={workspaceName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("config.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("config.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("config.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("config.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
