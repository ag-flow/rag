import { useRef, useState, type ChangeEvent, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { useImportSshKey } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ImportSshKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const mutation = useImportSshKey(vaultId);

  const [name, setName] = useState("");
  const [keyId, setKeyId] = useState("");
  const [privateKey, setPrivateKey] = useState("");
  const [publicKey, setPublicKey] = useState("");
  const [passphrase, setPassphrase] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  const privateFileRef = useRef<HTMLInputElement>(null);
  const publicFileRef = useRef<HTMLInputElement>(null);

  const harpoPath = keyId ? `/ssh/${keyId}/private_key` : "";

  function validateKeyId(v: string) {
    setKeyIdError(v && !KEY_ID_RE.test(v) ? t("ssh.field_key_id_help") : "");
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setName(""); setKeyId(""); setPrivateKey("");
      setPublicKey(""); setPassphrase(""); setKeyIdError("");
    }
  }

  function readFile(
    e: ChangeEvent<HTMLInputElement>,
    setter: (v: string) => void,
  ) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setter((ev.target?.result as string) ?? "");
    reader.readAsText(file);
  }

  const canSubmit =
    name.trim().length > 0 &&
    keyId.length > 0 &&
    KEY_ID_RE.test(keyId) &&
    privateKey.trim().length > 0 &&
    publicKey.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({
        key_id: keyId,
        name,
        private_key: privateKey,
        public_key: publicKey,
        passphrase: passphrase || null,
      });
      toast({ title: t("ssh.import_btn_submit") + " OK" });
      handleClose(false);
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
      <DialogContent className="sm:max-w-[540px]">
        <DialogHeader>
          <DialogTitle>{t("ssh.import_dialog_title")}</DialogTitle>
          <DialogDescription>{t("ssh.import_dialog_subtitle")}</DialogDescription>
        </DialogHeader>
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
              {t("ssh.field_private_key")}
            </Label>
            <div className="mt-1 flex flex-col gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => privateFileRef.current?.click()}
              >
                {t("ssh.choose_file")}
              </Button>
              <input
                ref={privateFileRef}
                type="file"
                accept=".pem,.key,id_rsa,id_ed25519,id_ecdsa"
                className="hidden"
                onChange={(e: ChangeEvent<HTMLInputElement>) => readFile(e, setPrivateKey)}
              />
              <Textarea
                value={privateKey}
                onChange={(e) => setPrivateKey(e.target.value)}
                placeholder="-----BEGIN OPENSSH PRIVATE KEY-----"
                className="font-mono text-xs min-h-[80px]"
              />
            </div>
            {harpoPath && (
              <p className="mt-1 text-xs text-slate-400">
                <span className="font-medium">{t("ssh.path_preview")}</span>{" "}
                <code className="font-mono">{harpoPath}</code>
              </p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_public_key")}
            </Label>
            <div className="mt-1 flex flex-col gap-2">
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="w-fit"
                onClick={() => publicFileRef.current?.click()}
              >
                {t("ssh.choose_file")}
              </Button>
              <input
                ref={publicFileRef}
                type="file"
                accept=".pub"
                className="hidden"
                onChange={(e: ChangeEvent<HTMLInputElement>) => readFile(e, setPublicKey)}
              />
              <Textarea
                value={publicKey}
                onChange={(e) => setPublicKey(e.target.value)}
                placeholder="ssh-ed25519 AAAA... or ssh-rsa AAAA..."
                className="font-mono text-xs min-h-[60px]"
              />
            </div>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("ssh.field_passphrase")}
            </Label>
            <Input
              type="password"
              value={passphrase}
              onChange={(e) => setPassphrase(e.target.value)}
              placeholder={t("ssh.field_passphrase_placeholder")}
              className="mt-1"
            />
          </div>

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("ssh.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("ssh.import_btn_submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
