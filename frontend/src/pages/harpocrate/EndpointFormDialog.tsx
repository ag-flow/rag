import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useProviderKeys } from "@/hooks/useHarpocrateVaults";
import { useCreateEndpoint, useUpdateEndpoint } from "@/hooks/useVaultEndpoints";
import { useToast } from "@/hooks/useToast";
import { slugifyLabel } from "@/lib/slugify";
import type { VaultEndpoint } from "@/lib/vault-endpoints.types";

interface Props {
  vaultId: string;
  endpoint: VaultEndpoint | null; // null = création
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

const NONE = "__none__";

export function EndpointFormDialog({ vaultId, endpoint, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: providerKeys = [] } = useProviderKeys(vaultId);
  const createMutation = useCreateEndpoint(vaultId);
  const updateMutation = useUpdateEndpoint(vaultId);

  const [label, setLabel] = useState("");
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("");
  const [apiKeyRef, setApiKeyRef] = useState<string>(NONE);
  const [baseUrl, setBaseUrl] = useState("");
  const [rerankOn, setRerankOn] = useState(false);
  const [rerankProvider, setRerankProvider] = useState("cohere");
  const [rerankModel, setRerankModel] = useState("");
  const [rerankKeyRef, setRerankKeyRef] = useState<string>(NONE);
  const [rerankBaseUrl, setRerankBaseUrl] = useState("");
  const [rerankTopK, setRerankTopK] = useState(20);

  // Pré-remplit en mode édition, reset en création.
  useEffect(() => {
    if (!open) return;
    setLabel(endpoint?.label ?? "");
    setProvider(endpoint?.indexer.provider ?? "openai");
    setModel(endpoint?.indexer.model ?? "");
    setApiKeyRef(endpoint?.indexer.api_key_ref ?? NONE);
    setBaseUrl(endpoint?.indexer.base_url ?? "");
    setRerankOn(endpoint?.rerank != null);
    setRerankProvider(endpoint?.rerank?.provider ?? "cohere");
    setRerankModel(endpoint?.rerank?.model ?? "");
    setRerankKeyRef(endpoint?.rerank?.api_key_ref ?? NONE);
    setRerankBaseUrl(endpoint?.rerank?.base_url ?? "");
    setRerankTopK(endpoint?.rerank?.top_k_pre_rerank ?? 20);
  }, [open, endpoint]);

  const slug = endpoint?.slug ?? slugifyLabel(label);
  const valid = label.trim().length > 0 && model.trim().length > 0 && slug.length > 0
    && (!rerankOn || rerankModel.trim().length > 0);

  function buildPayload() {
    return {
      label,
      indexer: {
        provider,
        model,
        api_key_ref: apiKeyRef === NONE ? null : apiKeyRef,
        base_url: baseUrl.trim() === "" ? null : baseUrl,
      },
      rerank: rerankOn
        ? {
            provider: rerankProvider,
            model: rerankModel,
            api_key_ref: rerankKeyRef === NONE ? null : rerankKeyRef,
            base_url: rerankBaseUrl.trim() === "" ? null : rerankBaseUrl,
            top_k_pre_rerank: rerankTopK,
          }
        : null,
    };
  }

  async function handleSubmit() {
    try {
      if (endpoint) {
        await updateMutation.mutateAsync({
          endpointId: endpoint.id,
          payload: { ...buildPayload(), clear_rerank: !rerankOn },
        });
        toast({ title: t("endpoints.updated_toast") });
      } else {
        await createMutation.mutateAsync(buildPayload());
        toast({ title: t("endpoints.created_toast") });
      }
      onOpenChange(false);
    } catch {
      toast({ title: t("endpoints.error_toast"), variant: "destructive" });
    }
  }

  const keySelect = (value: string, onChange: (v: string) => void, ariaLabel: string) => (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="mt-1" aria-label={ariaLabel}>
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value={NONE}>{t("endpoints.no_key")}</SelectItem>
        {providerKeys.map((k) => (
          <SelectItem key={k.harpo_path} value={k.harpo_path}>
            {k.label} ({k.provider})
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>
            {endpoint ? t("endpoints.edit_title") : t("endpoints.create_title")}
          </DialogTitle>
          <DialogDescription>{t("endpoints.form_desc")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("endpoints.field_label")}
            </Label>
            <Input
              value={label}
              onChange={(e) => setLabel(e.target.value)}
              placeholder={t("endpoints.field_label_placeholder")}
              className="mt-1"
              autoFocus
            />
            <p className="mt-1 font-mono text-xs text-slate-400">
              {t("endpoints.slug_preview", { slug: slug || "—" })}
            </p>
          </div>

          <fieldset className="rounded-md border border-slate-200 p-3">
            <legend className="px-1 text-xs font-semibold uppercase text-slate-500">
              {t("endpoints.vectorization")}
            </legend>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <Label className="text-xs text-slate-600">{t("endpoints.provider")}</Label>
                <Input value={provider} onChange={(e) => setProvider(e.target.value)}
                  className="mt-1 font-mono" placeholder="openai" />
              </div>
              <div>
                <Label className="text-xs text-slate-600">{t("endpoints.model")}</Label>
                <Input value={model} onChange={(e) => setModel(e.target.value)}
                  className="mt-1 font-mono" placeholder="text-embedding-3-small" />
              </div>
            </div>
            <div className="mt-3">
              <Label className="text-xs text-slate-600">{t("endpoints.api_key")}</Label>
              {keySelect(apiKeyRef, setApiKeyRef, t("endpoints.api_key"))}
            </div>
            <div className="mt-3">
              <Label className="text-xs text-slate-600">{t("endpoints.base_url")}</Label>
              <Input value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)}
                className="mt-1 font-mono" placeholder="http://ollama:11434 (optionnel)" />
            </div>
          </fieldset>

          <fieldset className="rounded-md border border-slate-200 p-3">
            <legend className="flex items-center gap-2 px-1 text-xs font-semibold uppercase text-slate-500">
              {t("endpoints.rerank")}
              <Switch checked={rerankOn} onCheckedChange={setRerankOn}
                aria-label={t("endpoints.rerank")} />
            </legend>
            {rerankOn && (
              <>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-slate-600">{t("endpoints.provider")}</Label>
                    <Input value={rerankProvider}
                      onChange={(e) => setRerankProvider(e.target.value)}
                      className="mt-1 font-mono" placeholder="cohere" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-600">{t("endpoints.model")}</Label>
                    <Input value={rerankModel} onChange={(e) => setRerankModel(e.target.value)}
                      className="mt-1 font-mono" placeholder="rerank-v3.5" />
                  </div>
                </div>
                <div className="mt-3">
                  <Label className="text-xs text-slate-600">{t("endpoints.api_key")}</Label>
                  {keySelect(rerankKeyRef, setRerankKeyRef, t("endpoints.rerank_api_key"))}
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3">
                  <div>
                    <Label className="text-xs text-slate-600">{t("endpoints.base_url")}</Label>
                    <Input value={rerankBaseUrl}
                      onChange={(e) => setRerankBaseUrl(e.target.value)}
                      className="mt-1 font-mono" />
                  </div>
                  <div>
                    <Label className="text-xs text-slate-600">{t("endpoints.top_k")}</Label>
                    <Input type="number" min={1} max={200} value={rerankTopK}
                      onChange={(e) => setRerankTopK(Number(e.target.value))}
                      className="mt-1" />
                  </div>
                </div>
              </>
            )}
          </fieldset>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("endpoints.cancel")}
          </Button>
          <Button type="button" onClick={() => void handleSubmit()}
            disabled={!valid || createMutation.isPending || updateMutation.isPending}>
            {endpoint ? t("endpoints.save") : t("endpoints.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
