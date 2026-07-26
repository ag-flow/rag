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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { useProviderKeys } from "@/hooks/useHarpocrateVaults";
import { useModels, useProviderUrlTemplates, useRerankPairings } from "@/hooks/useModels";
import { pairingNote, resolveCallUrl } from "@/lib/models";
import { RERANK_PROVIDERS } from "@/pages/workspace/WorkspaceRerankTab.schema";
import { vaultEndpointsApi, type SectionTestResult } from "@/lib/vault-endpoints";
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

// LLM d'exécution des prompts — mêmes providers que workspace_llm_configs.
const LLM_PROVIDERS = [
  "claude",
  "openai",
  "azure-openai",
  "ollama",
  "ollama-cloud",
  "gemini",
  "deepseek",
  "dashscope",
] as const;

type TestSection = "vectorization" | "rerank" | "llm";

export function EndpointFormDialog({ vaultId, endpoint, open, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: providerKeys = [] } = useProviderKeys(vaultId);
  const { data: models = [] } = useModels();
  const { data: rerankPairings = [] } = useRerankPairings();
  const { data: urlTemplates = {} } = useProviderUrlTemplates();
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
  const [llmOn, setLlmOn] = useState(false);
  const [llmProvider, setLlmProvider] = useState("ollama");
  const [llmModel, setLlmModel] = useState("");
  const [llmKeyRef, setLlmKeyRef] = useState<string>(NONE);
  const [llmBaseUrl, setLlmBaseUrl] = useState("");
  // Limites de débit par service — chaîne vide = règle désactivée.
  const [idxRpm, setIdxRpm] = useState("");
  const [idxTpm, setIdxTpm] = useState("");
  const [rerankRpm, setRerankRpm] = useState("");
  const [rerankTpm, setRerankTpm] = useState("");
  const [llmRpm, setLlmRpm] = useState("");
  const [llmTpm, setLlmTpm] = useState("");

  // Modèles LLM : la TABLE DES MODÈLES (page Models, kind='llm') est le
  // référentiel — comme la vectorisation. Repli saisie libre si vide.
  const llmModelOptions = models
    .filter((m) => m.kind === "llm" && m.provider === llmProvider)
    .map((m) => m.model)
    .sort();
  const llmModelChoices =
    llmModel && !llmModelOptions.includes(llmModel)
      ? [llmModel, ...llmModelOptions]
      : llmModelOptions;

  const [testing, setTesting] = useState<TestSection | null>(null);
  const [testResults, setTestResults] = useState<
    Partial<Record<TestSection, SectionTestResult>>
  >({});

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
    setLlmOn(endpoint?.llm != null);
    setLlmProvider(endpoint?.llm?.provider ?? "ollama");
    setLlmModel(endpoint?.llm?.model ?? "");
    setLlmKeyRef(endpoint?.llm?.api_key_ref ?? NONE);
    setLlmBaseUrl(endpoint?.llm?.base_url ?? "");
    setIdxRpm(endpoint?.indexer.rpm_limit != null ? String(endpoint.indexer.rpm_limit) : "");
    setIdxTpm(endpoint?.indexer.tpm_limit != null ? String(endpoint.indexer.tpm_limit) : "");
    setRerankRpm(endpoint?.rerank?.rpm_limit != null ? String(endpoint.rerank.rpm_limit) : "");
    setRerankTpm(endpoint?.rerank?.tpm_limit != null ? String(endpoint.rerank.tpm_limit) : "");
    setLlmRpm(endpoint?.llm?.rpm_limit != null ? String(endpoint.llm.rpm_limit) : "");
    setLlmTpm(endpoint?.llm?.tpm_limit != null ? String(endpoint.llm.tpm_limit) : "");
    setTestResults({});
  }, [open, endpoint]);

  // Défauts en création : premier couple provider/modèle du référentiel.
  useEffect(() => {
    if (!open || endpoint || models.length === 0 || model !== "") return;
    const first = models[0];
    if (first) {
      setProvider(first.provider);
      setModel(first.model);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, endpoint, models]);

  // Providers/modèles d'embedding depuis model_dimensions (référence backend).
  const embedProviders = [
    ...new Set(models.filter((m) => m.kind === "embedding").map((m) => m.provider)),
  ].sort();
  const embedModels = models
    .filter((m) => m.kind === "embedding" && m.provider === provider)
    .map((m) => m.model)
    .sort();
  // En édition, une valeur hors référentiel reste sélectionnable (pas de perte).
  const providerOptions =
    provider && !embedProviders.includes(provider) ? [provider, ...embedProviders] : embedProviders;
  const modelOptions =
    model && !embedModels.includes(model) ? [model, ...embedModels] : embedModels;
  // Modèles de rerank : la table des modèles (kind='rerank') est le
  // référentiel unique, filtré sur le provider choisi.
  const rerankModels = models
    .filter((m) => m.kind === "rerank" && m.provider === rerankProvider)
    .map((m) => m.model)
    .sort();
  const rerankModelOptions =
    rerankModel && !rerankModels.includes(rerankModel)
      ? [rerankModel, ...rerankModels]
      : rerankModels;
  // Préco : pairing embedder (onglet Vectorisation) → reranker validé
  // (référentiel rerank_pairings, migration 085).
  const precoNote = (rerankModelName: string): string | null =>
    pairingNote(
      rerankPairings,
      { provider, model },
      { provider: rerankProvider, model: rerankModelName },
    );
  const selectedPrecoNote = rerankModel ? precoNote(rerankModel) : null;

  // URL réelle d'appel affichée sous chaque champ Base URL. Le masque vient du
  // référentiel backend ; un url_template porté par le modèle du registre prime.
  function callUrlHint(
    capability: "embeddings" | "chat" | "rerank",
    providerName: string,
    modelName: string,
    baseUrlValue: string,
  ) {
    const registryEntry = models.find(
      (m) => m.provider === providerName && m.model === modelName,
    );
    const resolved = resolveCallUrl(urlTemplates, capability, {
      provider: providerName,
      model: modelName,
      baseUrl: baseUrlValue,
      template: registryEntry?.url_template ?? null,
    });
    const mask =
      (registryEntry?.url_template ?? "").trim() ||
      urlTemplates[providerName]?.[capability]?.template;
    if (!mask) return null;
    return (
      <p className="mt-1 text-xs text-slate-500">
        <span className="text-slate-400">{t("endpoints.call_url_mask")} :</span>{" "}
        <span className="font-mono">{mask}</span>
        <br />
        <span className="text-slate-400">{t("endpoints.call_url")} :</span>{" "}
        <span className="font-mono">{resolved ?? t("endpoints.call_url_missing_base")}</span>
      </p>
    );
  }

  // Règles de limites de débit d'un service : deux règles activables
  // (requêtes/min, tokens/min). Switch OFF → valeur vidée → null au save.
  function limitRules(
    rpm: string,
    setRpm: (v: string) => void,
    tpm: string,
    setTpm: (v: string) => void,
  ) {
    const rule = (
      value: string,
      setValue: (v: string) => void,
      labelKey: string,
      placeholder: string,
    ) => (
      <div className="flex items-center gap-2">
        <Switch
          checked={value !== ""}
          onCheckedChange={(on) => setValue(on ? placeholder : "")}
          aria-label={t(labelKey)}
        />
        <span className="w-40 text-xs text-slate-600">{t(labelKey)}</span>
        <Input
          type="number"
          min={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          disabled={value === ""}
          className="w-32"
        />
      </div>
    );
    return (
      <div className="mt-3 space-y-2 rounded-md border border-slate-200 bg-slate-50 p-3">
        <p className="text-xs font-medium text-slate-600">{t("endpoints.limits_title")}</p>
        {rule(rpm, setRpm, "endpoints.limit_rpm", "3000")}
        {rule(tpm, setTpm, "endpoints.limit_tpm", "500000")}
      </div>
    );
  }

  // Si le modèle du registre porte une URL de paramétrage SANS masque
  // (aucun placeholder {…}, ex. https://api.jina.ai/v1), elle est une base
  // directement utilisable : on préremplit le champ Base URL avec.
  function fillBaseUrlFromModel(
    providerName: string,
    modelName: string,
    setBase: (v: string) => void,
  ) {
    const entry = models.find((m) => m.provider === providerName && m.model === modelName);
    const tpl = (entry?.url_template ?? "").trim();
    if (tpl && !tpl.includes("{")) setBase(tpl);
  }

  function handleProviderChange(next: string) {
    setProvider(next);
    const first = models.find((m) => m.provider === next)?.model ?? "";
    setModel(first);
  }

  function handleRerankProviderChange(next: string) {
    setRerankProvider(next);
    const first = models
      .filter((m) => m.kind === "rerank" && m.provider === next)
      .map((m) => m.model)
      .sort()[0];
    setRerankModel(first ?? "");
  }

  const slug = endpoint?.slug ?? slugifyLabel(label);
  const valid =
    label.trim().length > 0 &&
    model.trim().length > 0 &&
    slug.length > 0 &&
    (!rerankOn || rerankModel.trim().length > 0) &&
    (!llmOn || llmModel.trim().length > 0);

  const limitOrNull = (v: string): number | null => {
    const n = Number(v.trim());
    return v.trim() !== "" && Number.isFinite(n) && n > 0 ? Math.floor(n) : null;
  };

  function buildPayload() {
    return {
      label,
      indexer: {
        provider,
        model,
        api_key_ref: apiKeyRef === NONE ? null : apiKeyRef,
        base_url: baseUrl.trim() === "" ? null : baseUrl,
        rpm_limit: limitOrNull(idxRpm),
        tpm_limit: limitOrNull(idxTpm),
      },
      rerank: rerankOn
        ? {
            provider: rerankProvider,
            model: rerankModel,
            api_key_ref: rerankKeyRef === NONE ? null : rerankKeyRef,
            base_url: rerankBaseUrl.trim() === "" ? null : rerankBaseUrl,
            top_k_pre_rerank: rerankTopK,
            rpm_limit: limitOrNull(rerankRpm),
            tpm_limit: limitOrNull(rerankTpm),
          }
        : null,
      llm: llmOn
        ? {
            provider: llmProvider,
            model: llmModel,
            api_key_ref: llmKeyRef === NONE ? null : llmKeyRef,
            base_url: llmBaseUrl.trim() === "" ? null : llmBaseUrl,
            rpm_limit: limitOrNull(llmRpm),
            tpm_limit: limitOrNull(llmTpm),
          }
        : null,
    };
  }

  async function handleSubmit() {
    try {
      if (endpoint) {
        await updateMutation.mutateAsync({
          endpointId: endpoint.id,
          payload: { ...buildPayload(), clear_rerank: !rerankOn, clear_llm: !llmOn },
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

  async function handleTest(section: TestSection) {
    setTesting(section);
    setTestResults((prev) => ({ ...prev, [section]: undefined }));
    try {
      const payload = buildPayload();
      const result = await vaultEndpointsApi.test(vaultId, {
        indexer: section === "vectorization" ? payload.indexer : null,
        rerank: section === "rerank" ? payload.rerank : null,
        llm: section === "llm" ? payload.llm : null,
      });
      const sectionResult =
        section === "vectorization" ? result.vectorization : result[section];
      if (sectionResult) {
        setTestResults((prev) => ({ ...prev, [section]: sectionResult }));
      }
    } catch {
      toast({ title: t("endpoints.test_error"), variant: "destructive" });
    } finally {
      setTesting(null);
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

  const testFooter = (section: TestSection, enabled: boolean) => {
    const result = testResults[section];
    return (
      <div className="mt-3 flex items-start justify-between gap-3 border-t pt-3">
        <div className="min-w-0 flex-1 text-xs">
          {result && (
            <p className={result.ok ? "text-emerald-700" : "text-rose-700"}>
              {result.ok ? "✓" : "✗"} {result.message}
            </p>
          )}
        </div>
        <Button
          type="button"
          variant="outline"
          size="sm"
          onClick={() => void handleTest(section)}
          disabled={!enabled || testing !== null}
        >
          {testing === section ? t("endpoints.testing") : t("endpoints.test_btn")}
        </Button>
      </div>
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] overflow-y-auto sm:max-w-[560px]">
        <DialogHeader>
          <DialogTitle>
            {endpoint ? t("endpoints.edit_title") : t("endpoints.create_title")}
          </DialogTitle>
          <DialogDescription>{t("endpoints.form_desc")}</DialogDescription>
        </DialogHeader>

        <div className="min-w-0 space-y-4">
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

          <Tabs defaultValue="vectorization">
            <TabsList>
              <TabsTrigger value="vectorization">{t("endpoints.vectorization")}</TabsTrigger>
              <TabsTrigger value="rerank">{t("endpoints.rerank")}</TabsTrigger>
              <TabsTrigger value="llm">{t("endpoints.llm")}</TabsTrigger>
            </TabsList>

            <TabsContent value="vectorization" className="rounded-md border p-3">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <Label className="text-xs text-slate-600">{t("endpoints.provider")}</Label>
                  <Select value={provider} onValueChange={handleProviderChange}>
                    <SelectTrigger className="mt-1" aria-label={t("endpoints.provider")}>
                      <SelectValue placeholder={t("endpoints.select_placeholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {providerOptions.map((pv) => (
                        <SelectItem key={pv} value={pv}>
                          {pv}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                <div>
                  <Label className="text-xs text-slate-600">{t("endpoints.model")}</Label>
                  <Select
                    value={model}
                    onValueChange={(m) => {
                      setModel(m);
                      fillBaseUrlFromModel(provider, m, setBaseUrl);
                    }}
                  >
                    <SelectTrigger className="mt-1" aria-label={t("endpoints.model")}>
                      <SelectValue placeholder={t("endpoints.select_placeholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {modelOptions.map((m) => (
                        <SelectItem key={m} value={m}>
                          {m}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
              <div className="mt-3">
                <Label className="text-xs text-slate-600">{t("endpoints.api_key")}</Label>
                {keySelect(apiKeyRef, setApiKeyRef, t("endpoints.api_key"))}
              </div>
              <div className="mt-3">
                <Label className="text-xs text-slate-600">{t("endpoints.base_url")}</Label>
                <Input
                  value={baseUrl}
                  onChange={(e) => setBaseUrl(e.target.value)}
                  className="mt-1 font-mono"
                  placeholder="http://ollama:11434 (optionnel)"
                />
                {callUrlHint("embeddings", provider, model, baseUrl)}
              </div>
              {limitRules(idxRpm, setIdxRpm, idxTpm, setIdxTpm)}
              {testFooter("vectorization", model.trim() !== "")}
            </TabsContent>

            <TabsContent value="rerank" className="rounded-md border p-3">
              <div className="flex items-center gap-2">
                <Switch
                  checked={rerankOn}
                  onCheckedChange={(v) => {
                    setRerankOn(v);
                    if (v && rerankModel === "") {
                      setRerankModel(rerankModels[0] ?? "");
                    }
                  }}
                  aria-label={t("endpoints.rerank")}
                />
                <span className="text-xs font-medium text-slate-600">
                  {t("endpoints.rerank_toggle")}
                </span>
              </div>
              {rerankOn && (
                <>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-slate-600">{t("endpoints.provider")}</Label>
                      <Select value={rerankProvider} onValueChange={handleRerankProviderChange}>
                        <SelectTrigger className="mt-1" aria-label={t("endpoints.provider")}>
                          <SelectValue placeholder={t("endpoints.select_placeholder")} />
                        </SelectTrigger>
                        <SelectContent>
                          {RERANK_PROVIDERS.map((pv) => (
                            <SelectItem key={pv} value={pv}>
                              {pv}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs text-slate-600">{t("endpoints.model")}</Label>
                      <Select
                        value={rerankModel}
                        onValueChange={(m) => {
                          setRerankModel(m);
                          fillBaseUrlFromModel(rerankProvider, m, setRerankBaseUrl);
                        }}
                        disabled={rerankModelOptions.length === 0}
                      >
                        <SelectTrigger className="mt-1" aria-label={t("endpoints.model")}>
                          <SelectValue placeholder={t("endpoints.select_placeholder")} />
                        </SelectTrigger>
                        <SelectContent>
                          {rerankModelOptions.map((m) => (
                            <SelectItem key={m} value={m}>
                              {precoNote(m) ? `${m} · ${t("endpoints.preco")}` : m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {selectedPrecoNote && (
                        <p className="mt-1 text-xs text-emerald-700">
                          ★ {selectedPrecoNote}
                        </p>
                      )}
                      {rerankModels.length === 0 && (
                        <p className="mt-1 text-xs text-slate-400">
                          {t("endpoints.rerank_models_hint")}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-3">
                    <Label className="text-xs text-slate-600">{t("endpoints.api_key")}</Label>
                    {keySelect(rerankKeyRef, setRerankKeyRef, t("endpoints.rerank_api_key"))}
                  </div>
                  <div className="mt-3">
                    <Label className="text-xs text-slate-600">{t("endpoints.base_url")}</Label>
                    <Input
                      value={rerankBaseUrl}
                      onChange={(e) => setRerankBaseUrl(e.target.value)}
                      className="mt-1 font-mono"
                    />
                    {callUrlHint("rerank", rerankProvider, rerankModel, rerankBaseUrl)}
                  </div>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-slate-600">{t("endpoints.top_k")}</Label>
                      <Input
                        type="number"
                        min={1}
                        max={200}
                        value={rerankTopK}
                        onChange={(e) => setRerankTopK(Number(e.target.value))}
                        className="mt-1"
                      />
                    </div>
                  </div>
                  {limitRules(rerankRpm, setRerankRpm, rerankTpm, setRerankTpm)}
                  {testFooter("rerank", rerankModel.trim() !== "")}
                </>
              )}
            </TabsContent>

            <TabsContent value="llm" className="rounded-md border p-3">
              <div className="flex items-center gap-2">
                <Switch
                  checked={llmOn}
                  onCheckedChange={setLlmOn}
                  aria-label={t("endpoints.llm")}
                />
                <span className="text-xs font-medium text-slate-600">
                  {t("endpoints.llm_toggle")}
                </span>
              </div>
              <p className="mt-1 text-xs text-slate-400">{t("endpoints.llm_help")}</p>
              {llmOn && (
                <>
                  <div className="mt-3 grid grid-cols-2 gap-3">
                    <div>
                      <Label className="text-xs text-slate-600">{t("endpoints.provider")}</Label>
                      <Select value={llmProvider} onValueChange={setLlmProvider}>
                        <SelectTrigger className="mt-1" aria-label={t("endpoints.llm_provider")}>
                          <SelectValue placeholder={t("endpoints.select_placeholder")} />
                        </SelectTrigger>
                        <SelectContent>
                          {LLM_PROVIDERS.map((pv) => (
                            <SelectItem key={pv} value={pv}>
                              {pv}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </div>
                    <div>
                      <Label className="text-xs text-slate-600">{t("endpoints.model")}</Label>
                      {/* TOUJOURS une liste : le référentiel est la table des
                          modèles (kind='llm', filtré sur le provider choisi) —
                          pas de saisie libre. Liste vide → déclarer le modèle
                          dans la page Models. */}
                      <Select
                        value={llmModel}
                        onValueChange={(m) => {
                          setLlmModel(m);
                          fillBaseUrlFromModel(llmProvider, m, setLlmBaseUrl);
                        }}
                        disabled={llmModelChoices.length === 0}
                      >
                        <SelectTrigger className="mt-1" aria-label={t("endpoints.llm_model")}>
                          <SelectValue placeholder={t("endpoints.select_placeholder")} />
                        </SelectTrigger>
                        <SelectContent>
                          {llmModelChoices.map((m) => (
                            <SelectItem key={m} value={m}>
                              {m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      {llmModelOptions.length === 0 && (
                        <p className="mt-1 text-xs text-slate-400">
                          {t("endpoints.llm_models_hint")}
                        </p>
                      )}
                    </div>
                  </div>
                  <div className="mt-3">
                    <Label className="text-xs text-slate-600">{t("endpoints.api_key")}</Label>
                    {keySelect(llmKeyRef, setLlmKeyRef, t("endpoints.llm_api_key"))}
                  </div>
                  <div className="mt-3">
                    <Label className="text-xs text-slate-600">{t("endpoints.base_url")}</Label>
                    <Input
                      value={llmBaseUrl}
                      onChange={(e) => setLlmBaseUrl(e.target.value)}
                      className="mt-1 font-mono"
                      placeholder="http://ollama:11434 (ollama / azure)"
                    />
                    {callUrlHint("chat", llmProvider, llmModel, llmBaseUrl)}
                  </div>
                  {limitRules(llmRpm, setLlmRpm, llmTpm, setLlmTpm)}
                  {testFooter("llm", llmModel.trim() !== "")}
                </>
              )}
            </TabsContent>
          </Tabs>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("endpoints.cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSubmit()}
            disabled={!valid || createMutation.isPending || updateMutation.isPending}
          >
            {endpoint ? t("endpoints.save") : t("endpoints.create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
