import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateGitCredential } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { GitHost } from "@/lib/harpocrate-vaults.types";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

const GIT_HOSTS: { value: GitHost; label: string }[] = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
  { value: "gitea", label: "Gitea" },
  { value: "bitbucket", label: "Bitbucket" },
  { value: "azure-devops", label: "Azure DevOps" },
];

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddGitKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useCreateGitCredential(vaultId);

  const [host, setHost] = useState<GitHost | "">("");
  const [keyId, setKeyId] = useState("");
  const [label, setLabel] = useState("");
  const [scopeUrl, setScopeUrl] = useState("");
  const [value, setValue] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  const harpoPath = host && keyId ? `/git/${host}/${keyId}` : "";

  function validateKeyId(v: string) {
    if (v && !KEY_ID_RE.test(v)) {
      setKeyIdError(t("gitkeys.field_key_id_help"));
    } else {
      setKeyIdError("");
    }
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setHost("");
      setKeyId("");
      setLabel("");
      setScopeUrl("");
      setValue("");
      setKeyIdError("");
    }
  }

  const canSubmit =
    !!host &&
    !!keyId &&
    KEY_ID_RE.test(keyId) &&
    label.trim().length > 0 &&
    value.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !host) return;
    try {
      await mutation.mutateAsync({
        key_id: keyId,
        label,
        host,
        scope_url: scopeUrl.trim() || null,
        value,
      });
      toast({ title: t("gitkeys.created_toast") });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("gitkeys.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("gitkeys.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("gitkeys.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_host")}
            </Label>
            <Select value={host} onValueChange={(v) => setHost(v as GitHost)}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="GitHub, GitLab, Gitea…" />
              </SelectTrigger>
              <SelectContent>
                {GIT_HOSTS.map((h) => (
                  <SelectItem key={h.value} value={h.value}>
                    {h.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_key_id")}
            </Label>
            <Input
              value={keyId}
              onChange={(e) => {
                setKeyId(e.target.value);
                validateKeyId(e.target.value);
              }}
              placeholder="prod-pat"
              className="mt-1 font-mono"
            />
            {keyIdError ? (
              <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">{t("gitkeys.field_key_id_help")}</p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_label")}
            </Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="GitHub myorg production"
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_scope_url")}
            </Label>
            <Input
              value={scopeUrl}
              onChange={(e) => setScopeUrl(e.target.value)}
              placeholder={t("gitkeys.field_scope_url_placeholder")}
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("gitkeys.field_value")}
            </Label>
            <Input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="ghp_…"
              className="mt-1 font-mono"
            />
          </div>

          {harpoPath && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <span className="font-medium">{t("gitkeys.path_preview")}</span>{" "}
              <code className="font-mono">{harpoPath}</code>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("gitkeys.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("gitkeys.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
