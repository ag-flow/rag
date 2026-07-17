import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Pencil, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
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
import { LoadingSpinner } from "@/components/LoadingSpinner";
import { useDeleteEndpoint, useVaultEndpoints } from "@/hooks/useVaultEndpoints";
import { useToast } from "@/hooks/useToast";
import { EndpointFormDialog } from "./EndpointFormDialog";
import type { VaultEndpoint } from "@/lib/vault-endpoints.types";

interface Props {
  vaultId: string;
}

export function VaultEndpointsTab({ vaultId }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: endpoints = [], isLoading } = useVaultEndpoints(vaultId);
  const deleteMutation = useDeleteEndpoint(vaultId);

  const [formOpen, setFormOpen] = useState(false);
  const [toEdit, setToEdit] = useState<VaultEndpoint | null>(null);
  const [toDelete, setToDelete] = useState<VaultEndpoint | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("endpoints.deleted_toast") });
    } catch {
      toast({ title: t("endpoints.error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-24 items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div>
      <div className="flex items-center justify-between">
        <p className="text-sm text-slate-500">{t("endpoints.intro")}</p>
        <Button
          type="button"
          onClick={() => {
            setToEdit(null);
            setFormOpen(true);
          }}
        >
          {t("endpoints.add_btn")}
        </Button>
      </div>

      {endpoints.length === 0 ? (
        <p className="mt-6 text-sm text-slate-500">{t("endpoints.empty")}</p>
      ) : (
        <div className="mt-4 rounded-md border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("endpoints.col_label")}</TableHead>
                <TableHead>{t("endpoints.col_vectorization")}</TableHead>
                <TableHead>{t("endpoints.col_rerank")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {endpoints.map((ep) => (
                <TableRow key={ep.id}>
                  <TableCell>
                    <span className="font-medium text-slate-800">{ep.label}</span>
                    <div className="font-mono text-xs text-slate-400">{ep.slug}</div>
                  </TableCell>
                  <TableCell>
                    <Badge variant="secondary">
                      {ep.indexer.provider}/{ep.indexer.model}
                    </Badge>
                  </TableCell>
                  <TableCell>
                    {ep.rerank ? (
                      <Badge variant="secondary">
                        {ep.rerank.provider}/{ep.rerank.model}
                      </Badge>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => {
                        setToEdit(ep);
                        setFormOpen(true);
                      }}
                      aria-label={t("endpoints.edit_btn")}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(ep)}
                      aria-label={t("endpoints.delete_btn")}
                    >
                      <Trash2 className="h-4 w-4 text-red-400" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <EndpointFormDialog
        vaultId={vaultId}
        endpoint={toEdit}
        open={formOpen}
        onOpenChange={setFormOpen}
      />

      <AlertDialog open={toDelete !== null} onOpenChange={(o) => !o && setToDelete(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("endpoints.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("endpoints.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("endpoints.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleDelete()}>
              {t("endpoints.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
