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
import { useCreateProviderKey } from "@/hooks/useHarpocrateVaults";
import { useModels } from "@/hooks/useModels";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";

const KEY_ID_RE = /^[a-zA-Z0-9_-]+$/;

interface Props {
  vaultId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddProviderKeyDialog({ vaultId, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: models = [] } = useModels();
  const mutation = useCreateProviderKey(vaultId);

  const [provider, setProvider] = useState("");
  const [keyId, setKeyId] = useState("");
  const [label, setLabel] = useState("");
  const [value, setValue] = useState("");
  const [keyIdError, setKeyIdError] = useState("");

  // Providers distincts depuis model_dimensions
  const providers = [...new Set(models.map((m) => m.provider))].sort();

  const harpoPath =
    provider && keyId ? `/${provider}/${keyId}` : "";

  function validateKeyId(v: string) {
    if (v && !KEY_ID_RE.test(v)) {
      setKeyIdError(t("apikeys.field_key_id_help"));
    } else {
      setKeyIdError("");
    }
  }

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setProvider("");
      setKeyId("");
      setLabel("");
      setValue("");
      setKeyIdError("");
    }
  }

  const canSubmit =
    !!provider &&
    !!keyId &&
    KEY_ID_RE.test(keyId) &&
    label.trim().length > 0 &&
    value.trim().length > 0 &&
    !mutation.isPending;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;
    try {
      await mutation.mutateAsync({ key_id: keyId, label, provider, value });
      toast({ title: t("apikeys.created_toast") });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("apikeys.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("apikeys.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("apikeys.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_provider")}
            </Label>
            <Select value={provider} onValueChange={setProvider}>
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="openai, voyage, mistral…" />
              </SelectTrigger>
              <SelectContent>
                {providers.map((p) => (
                  <SelectItem key={p} value={p}>
                    {p}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_key_id")}
            </Label>
            <Input
              value={keyId}
              onChange={(e) => {
                setKeyId(e.target.value);
                validateKeyId(e.target.value);
              }}
              placeholder="prod-openai"
              className="mt-1 font-mono"
            />
            {keyIdError ? (
              <p className="mt-1 text-xs text-rose-600">{keyIdError}</p>
            ) : (
              <p className="mt-1 text-xs text-slate-400">{t("apikeys.field_key_id_help")}</p>
            )}
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_label")}
            </Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder="OpenAI production"
              className="mt-1"
            />
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("apikeys.field_value")}
            </Label>
            <Input
              type="password"
              value={value}
              onChange={(e) => setValue(e.target.value)}
              placeholder="sk-…"
              className="mt-1 font-mono"
            />
          </div>

          {harpoPath && (
            <div className="rounded bg-slate-50 px-3 py-2 text-xs text-slate-500">
              <span className="font-medium">{t("apikeys.path_preview")}</span>{" "}
              <code className="font-mono">{harpoPath}</code>
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("apikeys.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("apikeys.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
