import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2 } from "lucide-react";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { usePrompts, useDeletePrompt } from "@/hooks/useEnrichments";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import { AddPromptDialog } from "./workspace/AddPromptDialog";
import type { PromptTemplate } from "@/lib/enrichments.types";

export function PromptsPage() {
  const { t } = useTranslation("prompts");
  const { toast } = useToast();
  const { data: prompts = [], isLoading } = usePrompts();
  const deleteMutation = useDeletePrompt();
  const [addOpen, setAddOpen] = useState(false);
  const [toDelete, setToDelete] = useState<PromptTemplate | null>(null);

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("error_referenced"), variant: "destructive" });
      } else {
        toast({ title: t("error_toast"), variant: "destructive" });
      }
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && prompts.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("col_name")}</TableHead>
                <TableHead>{t("col_language")}</TableHead>
                <TableHead>{t("col_metadata_key")}</TableHead>
                <TableHead>{t("col_result_type")}</TableHead>
                <TableHead>{t("col_description")}</TableHead>
                <TableHead className="w-16" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {prompts.map((p) => (
                <TableRow key={p.id}>
                  <TableCell className="font-mono text-sm">{p.name}</TableCell>
                  <TableCell>
                    <span className="rounded bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-700">
                      {p.language}
                    </span>
                  </TableCell>
                  <TableCell className="font-mono text-xs text-slate-600">
                    {p.metadata_key}
                  </TableCell>
                  <TableCell>
                    <span className={`rounded px-2 py-0.5 text-xs font-medium ${
                      p.result_type === "json"
                        ? "bg-amber-100 text-amber-700"
                        : "bg-slate-100 text-slate-700"
                    }`}>
                      {p.result_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-xs text-slate-400 max-w-[200px] truncate">
                    {p.description ?? "—"}
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(p)}
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

      <AddPromptDialog open={addOpen} onOpenChange={setAddOpen} />

      <AlertDialog open={!!toDelete} onOpenChange={(o) => { if (!o) setToDelete(null); }}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-rose-600 hover:bg-rose-700">
              {t("delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
