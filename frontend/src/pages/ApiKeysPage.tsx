import { Fragment, useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, XCircle, Pencil, Plug } from "lucide-react";
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
import { useRevokeUserApiKey, useUserApiKeys } from "@/hooks/useUserApiKeys";
import { useToast } from "@/hooks/useToast";
import { CreateUserApiKeyDialog } from "@/pages/apikeys/CreateUserApiKeyDialog";
import { RotateUserApiKeyDialog } from "@/pages/apikeys/RotateUserApiKeyDialog";
import { EditScopeDialog } from "@/pages/apikeys/EditScopeDialog";
import { McpClientPanel } from "@/pages/apikeys/McpClientPanel";
import type { KeyScope, UserApiKey } from "@/lib/user-api-keys.types";

const STATUS_COLORS: Record<string, string> = {
  active: "text-emerald-600",
  grace_period: "text-amber-500",
  revoked: "text-red-400",
  expired: "text-slate-400",
};

const SCOPE_VARIANTS: Record<KeyScope, "secondary" | "default" | "destructive"> = {
  read: "secondary",
  read_write: "default",
  admin: "destructive",
};

export function ApiKeysPage() {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const { data: keys = [], isLoading } = useUserApiKeys();
  const revokeMutation = useRevokeUserApiKey();

  const [createOpen, setCreateOpen] = useState(false);
  const [toRotate, setToRotate] = useState<UserApiKey | null>(null);
  const [toEdit, setToEdit] = useState<UserApiKey | null>(null);
  const [toRevoke, setToRevoke] = useState<UserApiKey | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  const toggleConnect = (id: string) => setExpandedId((cur) => (cur === id ? null : id));

  async function handleRevoke() {
    if (!toRevoke) return;
    try {
      await revokeMutation.mutateAsync(toRevoke.id);
      toast({ title: t("revoked_toast") });
    } catch {
      toast({ title: t("error_toast"), variant: "destructive" });
    } finally {
      setToRevoke(null);
    }
  }

  if (isLoading) {
    return (
      <div className="flex h-full items-center justify-center">
        <LoadingSpinner />
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-4xl p-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-slate-900">{t("page_title")}</h1>
          <p className="mt-1 text-sm text-slate-500">{t("page_subtitle")}</p>
        </div>
        <Button type="button" onClick={() => setCreateOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {keys.length === 0 ? (
        <p className="mt-8 text-sm text-slate-500">{t("empty")}</p>
      ) : (
        <div className="mt-6 rounded-md border bg-white">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("col_name")}</TableHead>
                <TableHead>{t("col_scope")}</TableHead>
                <TableHead>{t("col_status")}</TableHead>
                <TableHead>{t("col_created")}</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <Fragment key={k.id}>
                <TableRow>
                  <TableCell>
                    <span className="font-medium text-slate-800">{k.name}</span>
                    <span className="ml-2 font-mono text-xs text-slate-400">
                      {k.fingerprint_preview}
                    </span>
                  </TableCell>
                  <TableCell>
                    <Badge variant={SCOPE_VARIANTS[k.scope]}>{t(`scope.levels.${k.scope}.label`)}</Badge>
                  </TableCell>
                  <TableCell>
                    <span className={STATUS_COLORS[k.status] ?? ""}>{t(`status_${k.status}`)}</span>
                  </TableCell>
                  <TableCell className="text-sm text-slate-500">
                    {new Date(k.created_at).toLocaleDateString()}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => toggleConnect(k.id)}
                      aria-label={t("connect_btn")}
                      aria-expanded={expandedId === k.id}
                    >
                      <Plug
                        className={`h-4 w-4 ${expandedId === k.id ? "text-sky-600" : ""}`}
                      />
                    </Button>
                    {k.status === "active" && (
                      <>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setToEdit(k)}
                          aria-label={t("edit_scope_btn")}
                        >
                          <Pencil className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRotate(k)}
                          aria-label={t("rotate_btn")}
                        >
                          <RotateCcw className="h-4 w-4" />
                        </Button>
                        <Button
                          type="button"
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRevoke(k)}
                          aria-label={t("revoke_btn")}
                        >
                          <XCircle className="h-4 w-4 text-red-400" />
                        </Button>
                      </>
                    )}
                  </TableCell>
                </TableRow>
                {expandedId === k.id && (
                  <TableRow>
                    <TableCell colSpan={5} className="bg-slate-50/60 p-4">
                      <McpClientPanel />
                    </TableCell>
                  </TableRow>
                )}
                </Fragment>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CreateUserApiKeyDialog open={createOpen} onOpenChange={setCreateOpen} />
      <RotateUserApiKeyDialog apiKey={toRotate} onOpenChange={(o) => !o && setToRotate(null)} />
      <EditScopeDialog apiKey={toEdit} onOpenChange={(o) => !o && setToEdit(null)} />

      <AlertDialog open={toRevoke !== null} onOpenChange={(o) => !o && setToRevoke(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("revoke_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("revoke_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction onClick={() => void handleRevoke()}>
              {t("revoke_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
