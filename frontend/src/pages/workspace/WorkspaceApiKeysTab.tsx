import { useState } from "react";
import { useTranslation } from "react-i18next";
import { RotateCcw, XCircle, Copy, Check } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Table, TableBody, TableCell, TableHead, TableHeader, TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useWorkspaceApiKeys, useRevokeApiKey } from "@/hooks/useWorkspaceApiKeys";
import { useToast } from "@/hooks/useToast";
import { CreateApiKeyDialog } from "./CreateApiKeyDialog";
import { RotateWorkspaceApiKeyDialog } from "./RotateWorkspaceApiKeyDialog";
import type { ApiKey } from "@/lib/workspace-apikeys.types";

const STATUS_COLORS: Record<string, string> = {
  active: "text-emerald-600",
  grace_period: "text-amber-500",
  revoked: "text-red-400",
  expired: "text-slate-400",
};

interface Props {
  workspaceName: string;
  workspaceId: string;
}

export function WorkspaceApiKeysTab({ workspaceName, workspaceId }: Props) {
  const { t } = useTranslation("apikeys");
  const { toast } = useToast();
  const { data: keys = [], isLoading } = useWorkspaceApiKeys(workspaceName);
  const revokeMutation = useRevokeApiKey(workspaceName);

  const [createOpen, setCreateOpen] = useState(false);
  const [toRotate, setToRotate] = useState<ApiKey | null>(null);
  const [toRevoke, setToRevoke] = useState<ApiKey | null>(null);

  const [copiedUrl, setCopiedUrl] = useState(false);
  const [copiedConfig, setCopiedConfig] = useState(false);

  const publicUrl = (import.meta.env["VITE_PUBLIC_URL"] as string | undefined) ?? window.location.origin;
  const mcpUrl = `${publicUrl}/mcp/${workspaceId}`;
  const mcpConfig = JSON.stringify(
    {
      [workspaceName]: {
        url: mcpUrl,
        headers: { Authorization: "Bearer <votre-clé>" },
      },
    },
    null,
    2,
  );

  async function copyText(text: string, setCopied: (v: boolean) => void) {
    await navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  }

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

  function statusLabel(key: ApiKey) {
    if (key.status === "grace_period" && key.rotated_at) {
      const expires = new Date(key.rotated_at);
      expires.setHours(expires.getHours() + 72);
      const hoursLeft = Math.max(0, Math.round((expires.getTime() - Date.now()) / 3_600_000));
      return t("status_grace_period", { hours: hoursLeft });
    }
    return t(`status_${key.status}`);
  }

  return (
    <div className="space-y-4 pt-4">
      {/* Section Connexion MCP */}
      <section className="rounded-md border border-slate-200 bg-slate-50 p-4 space-y-3 mb-4">
        <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-500">
          {t("mcp_section_title")}
        </h3>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">{t("mcp_url_label")}</Label>
          <div className="flex items-center gap-2">
            <Input value={mcpUrl} readOnly className="font-mono text-xs bg-white" />
            <Button
              size="sm"
              variant="outline"
              onClick={() => { void copyText(mcpUrl, setCopiedUrl); }}
              className="shrink-0"
            >
              {copiedUrl ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
        <p className="text-xs text-slate-500">{t("mcp_token_hint")}</p>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">{t("mcp_config_label")}</Label>
          <div className="flex items-start gap-2">
            <textarea
              value={mcpConfig}
              readOnly
              rows={7}
              className="w-full rounded-md border border-slate-200 bg-white p-2 font-mono text-xs resize-none"
            />
            <Button
              size="sm"
              variant="outline"
              onClick={() => { void copyText(mcpConfig, setCopiedConfig); }}
              className="shrink-0 mt-0.5"
            >
              {copiedConfig ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
            </Button>
          </div>
        </div>
      </section>

      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreateOpen(true)}>
          {t("add_btn")}
        </Button>
      </div>

      {!isLoading && keys.length === 0 ? (
        <div className="rounded border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500">
          {t("empty")}
        </div>
      ) : (
        <div className="overflow-hidden rounded border border-slate-200">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>{t("col_name")}</TableHead>
                <TableHead>{t("col_fingerprint")}</TableHead>
                <TableHead>{t("col_status")}</TableHead>
                <TableHead>{t("col_created")}</TableHead>
                <TableHead className="w-28" />
              </TableRow>
            </TableHeader>
            <TableBody>
              {keys.map((k) => (
                <TableRow
                  key={k.id}
                  className={
                    k.status === "revoked" || k.status === "expired" ? "opacity-50" : ""
                  }
                >
                  <TableCell className="font-medium">{k.name}</TableCell>
                  <TableCell className="font-mono text-xs text-slate-500">
                    {k.fingerprint_preview}…
                  </TableCell>
                  <TableCell
                    className={`text-xs font-medium ${STATUS_COLORS[k.status] ?? ""}`}
                  >
                    {statusLabel(k)}
                  </TableCell>
                  <TableCell className="text-xs text-slate-400">
                    {new Date(k.created_at).toLocaleDateString("fr-FR")}
                  </TableCell>
                  <TableCell>
                    {(k.status === "active" || k.status === "grace_period") && (
                      <div className="flex items-center gap-1 justify-end">
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRotate(k)}
                          aria-label={t("rotate_btn")}
                        >
                          <RotateCcw className="h-3.5 w-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => setToRevoke(k)}
                          className="text-rose-600 hover:text-rose-700"
                          aria-label={t("revoke_btn")}
                        >
                          <XCircle className="h-3.5 w-3.5" />
                        </Button>
                      </div>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}

      <CreateApiKeyDialog
        workspaceName={workspaceName}
        open={createOpen}
        onOpenChange={setCreateOpen}
      />

      {toRotate && (
        <RotateWorkspaceApiKeyDialog
          workspaceName={workspaceName}
          keyId={toRotate.id}
          keyName={toRotate.name}
          open={!!toRotate}
          onOpenChange={(o) => { if (!o) setToRotate(null); }}
        />
      )}

      <AlertDialog
        open={!!toRevoke}
        onOpenChange={(o) => { if (!o) setToRevoke(null); }}
      >
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{t("revoke_confirm_title")}</AlertDialogTitle>
            <AlertDialogDescription>{t("revoke_confirm_body")}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{t("cancel")}</AlertDialogCancel>
            <AlertDialogAction
              onClick={handleRevoke}
              className="bg-rose-600 hover:bg-rose-700"
            >
              {t("revoke_btn")}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
