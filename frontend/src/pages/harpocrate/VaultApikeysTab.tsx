import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RefreshCw, Trash2 } from "lucide-react";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useDeleteProviderKey, useProviderKeys } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { ProviderApiKey } from "@/lib/harpocrate-vaults.types";
import { ApiError } from "@/lib/api";
import { AddProviderKeyDialog } from "./AddProviderKeyDialog";
import { ReplaceProviderKeyDialog } from "./ReplaceProviderKeyDialog";

interface Props {
  vaultId: string;
  vaultName: string;
}

export function VaultApikeysTab({ vaultId, vaultName }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: keys = [], isLoading } = useProviderKeys(vaultId);
  const deleteMutation = useDeleteProviderKey(vaultId);

  const [addOpen, setAddOpen] = useState(false);
  const [toReplace, setToReplace] = useState<ProviderApiKey | null>(null);
  const [toDelete, setToDelete] = useState<ProviderApiKey | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("apikeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("apikeys.add")}
        </Button>
      </div>

      {isLoading ? null : keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("apikeys.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("apikeys.col_key_id")}</TableHead>
                <TableHead>{t("apikeys.col_provider")}</TableHead>
                <TableHead>{t("apikeys.col_label")}</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                  <TableCell>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {k.provider}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{k.label}</TableCell>
                  <TableCell>
                    <div className="flex items-center gap-1 justify-end">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setToReplace(k)}
                        aria-label={t("apikeys.replace_btn")}
                      >
                        <RefreshCw className="h-3.5 w-3.5" />
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setToDelete(k)}
                        className="text-rose-600 hover:text-rose-700"
                        aria-label={t("apikeys.delete_btn")}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <AddProviderKeyDialog
        vaultId={vaultId}
        vaultName={vaultName}
        open={addOpen}
        onOpenChange={setAddOpen}
      />

      {toReplace && (
        <ReplaceProviderKeyDialog
          vaultId={vaultId}
          keyId={toReplace.id}
          keyLabel={toReplace.label}
          provider={toReplace.provider}
          open={!!toReplace}
          onOpenChange={(o) => {
            if (!o) setToReplace(null);
          }}
        />
      )}

      <AlertDialog
        open={!!toDelete}
        onOpenChange={(o) => {
          if (!o) setToDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("apikeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>
              {t("apikeys.delete_confirm_body")}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("apikeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {t("apikeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
