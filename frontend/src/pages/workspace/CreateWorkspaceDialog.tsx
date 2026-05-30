import { useState } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useCreateWorkspace } from "@/hooks/useWorkspaces";
import { useModels } from "@/hooks/useModels";
import { useProviderKeysByProvider } from "@/hooks/useHarpocrateVaults";
import { useToast } from "@/hooks/useToast";
import { workspaceCreateSchema } from "@/lib/validators";

type FormData = z.infer<typeof workspaceCreateSchema>;

const BASE_URL_PROVIDERS = ["ollama", "azure-openai"];
const NO_KEY_PROVIDERS = ["ollama"];

interface ProviderModelBlockProps {
  prefix: "indexer" | "rerank";
  label: string;
  form: ReturnType<typeof useForm<FormData>>;
  models: { provider: string; model: string }[];
}

function ProviderModelBlock({ prefix, label, form, models }: ProviderModelBlockProps) {
  const { t } = useTranslation("workspaces");
  const provider = useWatch({ control: form.control, name: `${prefix}.provider` as const });
  const providers = [...new Set(models.map((m) => m.provider))].sort();
  const filteredModels = models.filter((m) => m.provider === provider).map((m) => m.model);
  const needsUrl = BASE_URL_PROVIDERS.includes(provider ?? "");
  const needsKey = !NO_KEY_PROVIDERS.includes(provider ?? "");
  const { data: keys = [] } = useProviderKeysByProvider(needsKey && provider ? provider : null);

  return (
    <div className="space-y-3 rounded-md border bg-slate-50 p-4">
      <div className="text-xs font-bold uppercase tracking-wide text-slate-600">{label}</div>

      <div className="grid grid-cols-2 gap-3">
        <FormField
          control={form.control}
          name={`${prefix}.provider` as const}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("form.provider")}</FormLabel>
              <Select
                onValueChange={(v) => {
                  field.onChange(v);
                  const firstModel = models.find((m) => m.provider === v)?.model ?? "";
                  form.setValue(`${prefix}.model` as const, firstModel);
                  form.setValue(`${prefix}.api_key_ref` as const, null);
                }}
                value={field.value ?? ""}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={t("form.provider")} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {providers.map((p) => (
                    <SelectItem key={p} value={p}>{p}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name={`${prefix}.model` as const}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("form.model")}</FormLabel>
              <Select onValueChange={field.onChange} value={field.value ?? ""}>
                <FormControl>
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {filteredModels.map((m) => (
                    <SelectItem key={m} value={m}>{m}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      </div>

      {needsUrl && (
        <FormField
          control={form.control}
          name={`${prefix}.base_url` as const}
          render={({ field }) => (
            <FormItem>
              <FormLabel>
                {t("form.base_url")}{" "}
                <span className="font-normal text-slate-400">{t("form.base_url_optional")}</span>
              </FormLabel>
              <FormControl>
                <Input
                  placeholder="http://192.168.10.80:11434"
                  {...field}
                  value={field.value ?? ""}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />
      )}

      {needsKey && (
        <FormField
          control={form.control}
          name={`${prefix}.api_key_ref` as const}
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t("form.api_key_ref")}</FormLabel>
              {keys.length === 0 ? (
                <p className="text-xs text-amber-600 mt-1">{t("form.api_key_ref_none")}</p>
              ) : (
                <Select onValueChange={field.onChange} value={field.value ?? ""}>
                  <FormControl>
                    <SelectTrigger>
                      <SelectValue placeholder={t("form.api_key_ref_placeholder")} />
                    </SelectTrigger>
                  </FormControl>
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
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </div>
  );
}

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (ws: { name: string }) => void;
}

export function CreateWorkspaceDialog({ open, onOpenChange, onCreated }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const createMutation = useCreateWorkspace();
  const { data: models = [] } = useModels();
  const [showRerank, setShowRerank] = useState(false);

  const defaultProvider = [...new Set(models.map((m) => m.provider))].sort()[0] ?? "openai";
  const defaultModel = models.find((m) => m.provider === defaultProvider)?.model ?? "";

  const form = useForm<FormData>({
    resolver: zodResolver(workspaceCreateSchema),
    defaultValues: {
      name: "",
      indexer: { provider: defaultProvider, model: defaultModel, api_key_ref: null, base_url: null },
      rerank: null,
    },
  });

  function handleToggleRerank() {
    if (showRerank) {
      form.setValue("rerank", null);
    } else {
      form.setValue("rerank", {
        provider: defaultProvider,
        model: defaultModel,
        api_key_ref: null,
        base_url: null,
        top_k_pre_rerank: 50,
      });
    }
    setShowRerank(!showRerank);
  }

  async function onSubmit(values: FormData) {
    try {
      const resp = await createMutation.mutateAsync({
        name: values.name,
        indexer: {
          provider: values.indexer.provider,
          model: values.indexer.model,
          api_key_ref: values.indexer.api_key_ref ?? null,
          base_url: values.indexer.base_url ?? null,
        },
        rerank: values.rerank
          ? {
              provider: values.rerank.provider,
              model: values.rerank.model,
              api_key_ref: values.rerank.api_key_ref ?? null,
              base_url: values.rerank.base_url ?? null,
              top_k_pre_rerank: values.rerank.top_k_pre_rerank,
            }
          : undefined,
      });
      toast({ title: t("toasts.created", { name: resp.name }) });
      onOpenChange(false);
      form.reset();
      setShowRerank(false);
      onCreated?.({ name: resp.name });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[540px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{t("create")}</DialogTitle>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>{t("form.name")}</FormLabel>
                  <FormControl>
                    <Input placeholder="workspace1" {...field} />
                  </FormControl>
                  <FormMessage />
                </FormItem>
              )}
            />

            <ProviderModelBlock
              prefix="indexer"
              label={t("form.indexer_section")}
              form={form}
              models={models}
            />

            {showRerank && (
              <>
                <ProviderModelBlock
                  prefix="rerank"
                  label={t("form.rerank_section")}
                  form={form}
                  models={models}
                />
                <FormField
                  control={form.control}
                  name="rerank.top_k_pre_rerank"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.top_k")}</FormLabel>
                      <FormControl>
                        <Input
                          type="number"
                          min={1}
                          max={500}
                          {...field}
                          value={field.value ?? 50}
                          onChange={(e) => field.onChange(parseInt(e.target.value, 10))}
                          className="w-32"
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  onClick={handleToggleRerank}
                  className="text-slate-500 text-xs"
                >
                  {t("form.rerank_remove")}
                </Button>
              </>
            )}

            {!showRerank && (
              <Button type="button" variant="outline" size="sm" onClick={handleToggleRerank}>
                + {t("form.rerank_section")}
              </Button>
            )}

            <DialogFooter>
              <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
                {t("common:buttons.cancel")}
              </Button>
              <Button type="submit" disabled={createMutation.isPending}>
                {t("common:buttons.create")}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
