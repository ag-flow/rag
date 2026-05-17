import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
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
  FormDescription,
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
import { z } from "zod";
import { useCreateWorkspace } from "@/hooks/useWorkspaces";
import { workspaceCreateSchema } from "@/lib/validators";
import { useToast } from "@/hooks/useToast";

type WorkspaceFormData = z.infer<typeof workspaceCreateSchema>;

const MODELS_BY_PROVIDER: Record<string, string[]> = {
  openai: ["text-embedding-3-small", "text-embedding-3-large"],
  voyage: ["voyage-3", "voyage-3-lite"],
  ollama: ["nomic-embed-text", "mxbai-embed-large"],
};

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function WorkspaceCreateDialog({ open, onOpenChange }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const createMutation = useCreateWorkspace();

  const form = useForm<WorkspaceFormData>({
    resolver: zodResolver(workspaceCreateSchema),
    defaultValues: {
      name: "",
      indexer: {
        provider: "openai",
        model: "text-embedding-3-small",
        api_key_ref: "",
      },
    },
  });

  const provider = form.watch("indexer.provider");
  const models = MODELS_BY_PROVIDER[provider] ?? [];

  async function onSubmit(values: WorkspaceFormData) {
    try {
      const payload = {
        ...values,
        indexer: {
          ...values.indexer,
          api_key_ref: values.indexer.api_key_ref ?? null,
          base_url: values.indexer.base_url ?? null,
        },
      };
      const resp = await createMutation.mutateAsync(payload);
      toast({ title: t("toasts.created", { name: resp.name }) });
      onOpenChange(false);
      form.reset();
    } catch {
      toast({
        title: t("common:errors.generic"),
        variant: "destructive",
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
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
                    <Input placeholder="harpocrate" {...field} />
                  </FormControl>
                  <FormDescription>{t("form.name_help")}</FormDescription>
                  <FormMessage />
                </FormItem>
              )}
            />

            <div className="border-t pt-4">
              <div className="text-xs font-bold uppercase tracking-wide text-slate-600 mb-3">
                {t("form.indexer")}
              </div>

              <div className="grid grid-cols-2 gap-3">
                <FormField
                  control={form.control}
                  name="indexer.provider"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.provider")}</FormLabel>
                      <Select
                        onValueChange={(v) => {
                          field.onChange(v);
                          form.setValue("indexer.model", MODELS_BY_PROVIDER[v]?.[0] ?? "");
                        }}
                        defaultValue={field.value}
                      >
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="openai">openai</SelectItem>
                          <SelectItem value="voyage">voyage</SelectItem>
                          <SelectItem value="ollama">ollama</SelectItem>
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="indexer.model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("form.model")}</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          {models.map((m) => (
                            <SelectItem key={m} value={m}>
                              {m}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </FormItem>
                  )}
                />
              </div>

              {provider !== "ollama" && (
                <FormField
                  control={form.control}
                  name="indexer.api_key_ref"
                  render={({ field }) => (
                    <FormItem className="mt-3">
                      <FormLabel>{t("form.api_key_ref")}</FormLabel>
                      <FormControl>
                        <Input placeholder="openai_embedding_key" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}

              {provider === "ollama" && (
                <FormField
                  control={form.control}
                  name="indexer.base_url"
                  render={({ field }) => (
                    <FormItem className="mt-3">
                      <FormLabel>
                        {t("form.base_url")}{" "}
                        <span className="text-slate-400 font-normal">
                          {t("form.base_url_optional")}
                        </span>
                      </FormLabel>
                      <FormControl>
                        <Input placeholder="http://192.168.10.80:11434" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              )}
            </div>

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
