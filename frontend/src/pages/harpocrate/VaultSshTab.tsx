import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Trash2, Copy, Check } from "lucide-react";
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
import { useDeleteSshKey, useSshKeys } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { SshKey } from "@/lib/harpocrate-vaults.types";
import { ImportSshKeyDialog } from "./ImportSshKeyDialog";
import { GenerateSshKeyDialog } from "./GenerateSshKeyDialog";

interface Props {
  vaultId: string;
}

export function VaultSshTab({ vaultId }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();

  const { data: keys = [], isLoading } = useSshKeys(vaultId);
  const deleteMutation = useDeleteSshKey(vaultId);

  const [importOpen, setImportOpen] = useState(false);
  const [generateOpen, setGenerateOpen] = useState(false);
  const [toDelete, setToDelete] = useState<SshKey | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  async function handleCopy(key: SshKey) {
    await navigator.clipboard.writeText(key.public_key);
    setCopiedId(key.id);
    toast({ title: t("ssh.copied_toast") });
    setTimeout(() => setCopiedId(null), 2000);
  }

  async function handleDelete() {
    if (!toDelete) return;
    try {
      await deleteMutation.mutateAsync(toDelete.id);
      toast({ title: t("ssh.deleted_toast") });
    } catch {
      toast({ title: t("ssh.error_toast"), variant: "destructive" });
    } finally {
      setToDelete(null);
    }
  }

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center justify-end gap-2">
        <Button size="sm" variant="outline" onClick={() => setImportOpen(true)}>
          {t("ssh.import_btn")}
        </Button>
        <Button size="sm" onClick={() => setGenerateOpen(true)}>
          {t("ssh.generate_btn")}
        </Button>
      </div>

      {!isLoading && keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("ssh.empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("ssh.col_key_id")}</TableHead>
                <TableHead>{t("ssh.col_type")}</TableHead>
                <TableHead>{t("ssh.col_name")}</TableHead>
                <TableHead>{t("ssh.col_public_key")}</TableHead>
                <TableHead className="w-20" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow key={k.id}>
                  <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                  <TableCell>
                    <span className="rounded bg-violet-100 px-2 py-0.5 text-xs font-medium text-violet-700">
                      {k.key_type}
                    </span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-600">{k.name}</TableCell>
                  <TableCell className="max-w-[200px]">
                    <div className="flex items-center gap-2">
                      <span className="truncate font-mono text-xs text-slate-500">
                        {k.public_key.slice(0, 40)}…
                      </span>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopy(k)}
                        aria-label={t("ssh.copy_public_key")}
                      >
                        {copiedId === k.id ? (
                          <Check className="h-3.5 w-3.5 text-green-600" />
                        ) : (
                          <Copy className="h-3.5 w-3.5" />
                        )}
                      </Button>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setToDelete(k)}
                      className="text-rose-600 hover:text-rose-700"
                      aria-label={t("ssh.delete_btn")}
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

      <ImportSshKeyDialog
        vaultId={vaultId}
        open={importOpen}
        onOpenChange={setImportOpen}
      />

      <GenerateSshKeyDialog
        vaultId={vaultId}
        open={generateOpen}
        onOpenChange={setGenerateOpen}
      />

      <AlertDialog
        open={!!toDelete}
        onOpenChange={(o) => {
          if (!o) setToDelete(null);
        }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("ssh.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("ssh.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("ssh.cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleDelete}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {t("ssh.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
