import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { Copy, Check } from "lucide-react";
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
import { Textarea } from "@/components/ui/textarea";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useGenerateSshKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { SshKeyType } from "@/lib/harpocrate-vaults.types";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

const KEY_TYPES: { value: SshKeyType; label: string }[] = [
  { value: "ed25519", label: "Ed25519 (recommandé)" },
  { value: "rsa-4096", label: "RSA-4096" },
  { value: "ecdsa-256", label: "ECDSA-256" },
];

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function GenerateSshKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useGenerateSshKey(vaultId);

  const [name, setName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [keyType, setKeyType] = useState<SshKeyType>("ed25519");
  const [keyIdError, setKeyIdError] = useState("");
  const [generatedPublicKey, setGeneratedPublicKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function validateKeyId(v: string) {
    setKeyIdError(v && !KEY_ID_RE.test(v) ? t("ssh.field_key_id_help") : "");
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setKeyId(""); setKeyType("ed25519");
      setKeyIdError(""); setGeneratedPublicKey(null); setCopied(false);
    }
  }

  async function handleCopy() {
    if (!generatedPublicKey) return;
    await navigator.clipboard.writeText(generatedPublicKey);
    setCopied(true);
    toast({ title: t("ssh.copied_toast") });
    setTimeout(() => setCopied(false), 2000);
  }

  const canSubmit =
    name.trim().length > 0 &&
    keyId.length > 0 &&
    KEY_ID_RE.test(keyId) &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      const result = await mutation.mutateAsync({ key_id: keyId, name, key_type: keyType });
      setGeneratedPublicKey(result.public_key);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("ssh.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("ssh.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("ssh.generate_dialog_title")}</DialogTitle>
        </DialogHeader>

        {generatedPublicKey ? (
          <div className="space-y-4">
            <div>
              <p className="text-sm font-medium text-slate-700">
                {t("ssh.generated_public_key_title")}
              </p>
              <p className="mt-1 text-xs text-slate-500">{t("ssh.generated_public_key_help")}</p>
              <Textarea
                value={generatedPublicKey}
                readOnly
                className="mt-2 font-mono text-xs min-h-[80px] bg-slate-50"
              />
            </div>
            <DialogFooter>
              <Button type="button" onClick={handleCopy} className="gap-2">
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                {t("ssh.copy_public_key")}
              </Button>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("ssh.close")}
              </Button>
            </DialogFooter>
          </div>
        ) : (
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_name")}
              </Label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="Déploiement production"
                className="mt-1"
              />
            </div>

            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_key_id")}
              </Label>
              <Input
                value={keyId}
                onChange={(e) => { setKeyId(e.target.value); validateKeyId(e.target.value); }}
                placeholder="deploy-prod"
                className="mt-1 font-mono"
              />
              {keyIdError ? (
                <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
              ) : (
                <p className="mt-1 text-xs text-slate-400">{t("ssh.field_key_id_help")}</p>
              )}
            </div>

            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("ssh.field_key_type")}
              </Label>
              <Select value={keyType} onValueChange={(v) => setKeyType(v as SshKeyType)}>
                <SelectTrigger className="mt-1">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {KEY_TYPES.map((k) => (
                    <SelectItem key={k.value} value={k.value}>
                      {k.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => handleClose(false)}>
                {t("ssh.cancel")}
              </Button>
              <Button type="submit" disabled={!canSubmit}>
                {mutation.isPending ? "…" : t("ssh.generate_btn_submit")}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  );
}
