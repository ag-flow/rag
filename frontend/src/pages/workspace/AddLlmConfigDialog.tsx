import { useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Select, SelectContent, SelectItem, SelectTrigger, SelectValue,
} from "@/components/ui/select";
import { useAddLlmConfig } from "@/hooks/usePlayground";
import { useProviderKeysByProvider } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { ApiError } from "@/lib/api";
import type { LlmProvider } from "@/lib/playground.types";

const PROVIDERS: { value: LlmProvider; label: string }[] = [
  { value: "claude", label: "Claude (Anthropic)" },
  { value: "openai", label: "OpenAI" },
  { value: "azure-openai", label: "Azure OpenAI" },
  { value: "ollama", label: "Ollama (local)" },
];

const MODELS_BY_PROVIDER: Record<LlmProvider, string[]> = {
  claude: ["claude-sonnet-4-5", "claude-opus-4-5"],
  openai: ["gpt-4o", "gpt-4o-mini", "o1"],
  "azure-openai": ["gpt-4o", "gpt-4o-mini"],
  ollama: [],
};

const NEEDS_BASE_URL: LlmProvider[] = ["azure-openai", "ollama"];
const NO_KEY_PROVIDERS: LlmProvider[] = ["ollama"];

interface Props {
  workspaceName: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function AddLlmConfigDialog({ workspaceName, open, onOpenChange }: Props) {
  const { t } = useTranslation("playground");
  const { toast } = useToast();
  const mutation = useAddLlmConfig(workspaceName);

  const [provider, setProvider] = useState<LlmProvider | "">("");
  const [model, setModel] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [ollamaModel, setOllamaModel] = useState("");
  const [selectedKey, setSelectedKey] = useState("");

  const needsKey = provider && !NO_KEY_PROVIDERS.includes(provider as LlmProvider);
  const needsBaseUrl = provider && NEEDS_BASE_URL.includes(provider as LlmProvider);
  const { data: keys = [] } = useProviderKeysByProvider(needsKey ? provider : null);

  function handleClose(next: boolean) {
    onOpenChange(next);
    if (!next) {
      setProvider(""); setModel(""); setBaseUrl(""); setSelectedKey(""); setOllamaModel("");
    }
  }

  const effectiveModel = provider === "ollama" ? ollamaModel : model;
  const canSubmit =
    !!provider && !!effectiveModel && !mutation.isPending &&
    (!needsBaseUrl || !!baseUrl) &&
    (!needsKey || keys.length === 0 || !!selectedKey);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!canSubmit || !provider) return;
    try {
      await mutation.mutateAsync({
        provider: provider as LlmProvider,
        model: effectiveModel,
        base_url: baseUrl || null,
        api_key_ref: selectedKey || null,
        enabled: true,
      });
      handleClose(false);
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        toast({ title: t("config.error_duplicate"), variant: "destructive" });
      } else {
        toast({ title: t("config.error_toast"), variant: "destructive" });
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("config.add_dialog_title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("config.field_provider")}
            </Label>
            <Select
              value={provider}
              onValueChange={(v) => {
                setProvider(v as LlmProvider);
                setModel("");
                setSelectedKey("");
              }}
            >
              <SelectTrigger className="mt-1">
                <SelectValue placeholder="Claude, OpenAI…" />
              </SelectTrigger>
              <SelectContent>
                {PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>{p.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          {provider && provider !== "ollama" && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_model")}
              </Label>
              <Select value={model} onValueChange={setModel}>
                <SelectTrigger className="mt-1 font-mono">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {MODELS_BY_PROVIDER[provider as LlmProvider].map((m) => (
                    <SelectItem key={m} value={m} className="font-mono">{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          )}

          {provider === "ollama" && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_model")}
              </Label>
              <Input
                value={ollamaModel}
                onChange={(e) => setOllamaModel(e.target.value)}
                placeholder="llama3, mistral…"
                className="mt-1 font-mono"
              />
            </div>
          )}

          {needsBaseUrl && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_base_url")}
              </Label>
              <Input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder={t("config.field_base_url_placeholder")}
                className="mt-1 font-mono"
              />
            </div>
          )}

          {needsKey && (
            <div>
              <Label className="text-xs uppercase tracking-wider text-slate-600">
                {t("config.field_key")}
              </Label>
              {keys.length === 0 ? (
                <p className="text-xs text-amber-600 mt-1">{t("config.field_key_none")}</p>
              ) : (
                <Select value={selectedKey} onValueChange={setSelectedKey}>
                  <SelectTrigger className="mt-1">
                    <SelectValue placeholder="Selectionner une cle…" />
                  </SelectTrigger>
                  <SelectContent>
                    {keys.map((k) => (
                      <SelectItem key={k.id} value={k.harpo_path}>
                        <span className="font-medium">{k.label}</span>
                        <span className="ml-2 text-xs text-slate-400">
                          {k.vault_label} · {k.key_id}
                        </span>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => handleClose(false)}>
              {t("config.cancel")}
            </Button>
            <Button type="submit" disabled={!canSubmit}>
              {t("config.save")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
