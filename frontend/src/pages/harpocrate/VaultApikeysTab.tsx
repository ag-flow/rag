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
import {
  useDeleteProviderKey,
  useDeleteGitCredential,
  useGitCredentials,
  useProviderKeys,
} from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import type { GitCredential, ProviderApiKey } from "@/lib/harpocrate-vaults.types";
import { ApiError } from "@/lib/api";
import { AddProviderKeyDialog } from "./AddProviderKeyDialog";
import { ReplaceProviderKeyDialog } from "./ReplaceProviderKeyDialog";
import { AddGitKeyDialog } from "./AddGitKeyDialog";
import { ReplaceGitKeyDialog } from "./ReplaceGitKeyDialog";

interface Props {
  vaultId: string;
}

export function VaultApikeysTab({ vaultId }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();

  const { data: providerKeys = [], isLoading: loadingProvider } = useProviderKeys(vaultId);
  const deleteProviderMutation = useDeleteProviderKey(vaultId);
  const [addProviderOpen, setAddProviderOpen] = useState(false);
  const [toReplaceProvider, setToReplaceProvider] = useState<ProviderApiKey | null>(null);
  const [toDeleteProvider, setToDeleteProvider] = useState<ProviderApiKey | null>(null);

  const { data: gitKeys = [], isLoading: loadingGit } = useGitCredentials(vaultId);
  const deleteGitMutation = useDeleteGitCredential(vaultId);
  const [addGitOpen, setAddGitOpen] = useState(false);
  const [toReplaceGit, setToReplaceGit] = useState<GitCredential | null>(null);
  const [toDeleteGit, setToDeleteGit] = useState<GitCredential | null>(null);

  async function handleDeleteProvider() {
    if (!toDeleteProvider) return;
    try {
      await deleteProviderMutation.mutateAsync(toDeleteProvider.id);
      toast({ title: t("apikeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDeleteProvider(null);
    }
  }

  async function handleDeleteGit() {
    if (!toDeleteGit) return;
    try {
      await deleteGitMutation.mutateAsync(toDeleteGit.id);
      toast({ title: t("gitkeys.deleted_toast") });
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("gitkeys.delete_referenced_error"), variant: "destructive" });
      } else {
        toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
      }
    } finally {
      setToDeleteGit(null);
    }
  }

  return (
    <div className="space-y-8 pt-4">
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">{t("tabs.apikeys")}</h3>
          <Button size="sm" onClick={() => setAddProviderOpen(true)}>
            {t("apikeys.add")}
          </Button>
        </div>

        {!loadingProvider && providerKeys.length === 0 ? (
          <div className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
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
                {providerKeys.map((k) => (
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
                          onClick={() => setToReplaceProvider(k)}
                          aria-label={t("apikeys.replace_btn")}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToDeleteProvider(k)}
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
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-700">{t("gitkeys.section_title")}</h3>
          <Button size="sm" onClick={() => setAddGitOpen(true)}>
            {t("gitkeys.add")}
          </Button>
        </div>

        {!loadingGit && gitKeys.length === 0 ? (
          <div className="rounded border border-dashed border-slate-300 p-6 text-center text-sm text-slate-500">
            {t("gitkeys.empty")}
          </div>
        ) : (
          <div className="overflow-hidden rounded border border-slate-200">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>{t("gitkeys.col_key_id")}</TableHead>
                  <TableHead>{t("gitkeys.col_host")}</TableHead>
                  <TableHead>{t("gitkeys.col_label")}</TableHead>
                  <TableHead>{t("gitkeys.col_scope_url")}</TableHead>
                  <TableHead className="w-28" />
                </TableRow>
              </TableHeader>
              <TableBody>
                {gitKeys.map((k) => (
                  <TableRow key={k.id}>
                    <TableCell className="font-mono text-sm">{k.key_id}</TableCell>
                    <TableCell>
                      <span className="rounded bg-sky-100 px-2 py-0.5 text-xs font-medium text-sky-700">
                        {k.host}
                      </span>
                    </TableCell>
                    <TableCell className="text-sm text-slate-600">{k.label}</TableCell>
                    <TableCell className="text-xs text-slate-400 font-mono">
                      {k.scope_url ?? "—"}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToReplaceGit(k)}
                          aria-label={t("gitkeys.replace_btn")}
                        >
                          <RefreshCw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToDeleteGit(k)}
                          className="text-rose-600 hover:text-rose-700"
                          aria-label={t("gitkeys.delete_btn")}
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
      </div>

      <AddProviderKeyDialog
        vaultId={vaultId}
        open={addProviderOpen}
        onOpenChange={setAddProviderOpen}
      />

      {toReplaceProvider && (
        <ReplaceProviderKeyDialog
          vaultId={vaultId}
          keyId={toReplaceProvider.id}
          keyLabel={toReplaceProvider.label}
          provider={toReplaceProvider.provider}
          open={!!toReplaceProvider}
          onOpenChange={(o) => { if (!o) setToReplaceProvider(null); }}
        />
      )}

      <AlertDialog
        open={!!toDeleteProvider}
        onOpenChange={(o) => { if (!o) setToDeleteProvider(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("apikeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("apikeys.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("apikeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteProvider} className="bg-rose-600 hover:bg-rose-700">
              {t("apikeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AddGitKeyDialog
        vaultId={vaultId}
        open={addGitOpen}
        onOpenChange={setAddGitOpen}
      />

      {toReplaceGit && (
        <ReplaceGitKeyDialog
          vaultId={vaultId}
          keyId={toReplaceGit.id}
          keyLabel={toReplaceGit.label}
          host={toReplaceGit.host}
          open={!!toReplaceGit}
          onOpenChange={(o) => { if (!o) setToReplaceGit(null); }}
        />
      )}

      <AlertDialog
        open={!!toDeleteGit}
        onOpenChange={(o) => { if (!o) setToDeleteGit(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("gitkeys.delete_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("gitkeys.delete_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("gitkeys.cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteGit} className="bg-rose-600 hover:bg-rose-700">
              {t("gitkeys.delete_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
