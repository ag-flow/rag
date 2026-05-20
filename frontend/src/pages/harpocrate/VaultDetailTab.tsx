import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
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
import { useUpdateVault } from "@/hooks/useHarpocrateVaults";
import { vaultUpdateSchema, type VaultUpdateForm } from "@/lib/validators";
import { useToast } from "@/hooks/useToast";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface VaultDetailTabProps {
  vault: VaultSummary;
  onReplaceApiKey: () => void;
  onReveal: () => void;
  onRetire: () => void;
}

export function VaultDetailTab({
  vault,
  onReplaceApiKey,
  onReveal,
  onRetire,
}: VaultDetailTabProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const updateMutation = useUpdateVault(vault.id);

  const form = useForm<VaultUpdateForm>({
    resolver: zodResolver(vaultUpdateSchema),
    defaultValues: {
      label: vault.label,
      base_url: vault.base_url,
      probe_path: vault.probe_path ?? "",
    },
  });

  // Reset le form quand le vault change (autre coffre sélectionné).
  useEffect(() => {
    form.reset({
      label: vault.label,
      base_url: vault.base_url,
      probe_path: vault.probe_path ?? "",
    });
  }, [vault.id, vault.label, vault.base_url, vault.probe_path, form]);

  async function onSubmit(values: VaultUpdateForm) {
    try {
      await updateMutation.mutateAsync({
        label: values.label,
        base_url: values.base_url,
        probe_path: values.probe_path === "" ? null : values.probe_path,
      });
      toast({ title: t("detail.saved_toast") });
    } catch {
      toast({
        title: t("detail.save_error_toast"),
        variant: "destructive",
      });
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
        <div className="grid grid-cols-2 gap-4">
          <div>
            <FormLabel className="text-xs uppercase tracking-wider text-slate-600">
              {t("detail.name_label")}
            </FormLabel>
            <Input
              value={vault.name}
              disabled
              className="mt-1 font-mono text-slate-400 bg-slate-50"
            />
          </div>

          <FormField
            control={form.control}
            name="label"
            render={({ field }) => (
              <FormItem>
                <FormLabel className="text-xs uppercase tracking-wider text-slate-600">
                  {t("detail.label_label")}
                </FormLabel>
                <FormControl>
                  <Input {...field} className="mt-1" />
                </FormControl>
                <FormMessage />
              </FormItem>
            )}
          />
        </div>

        <FormField
          control={form.control}
          name="base_url"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs uppercase tracking-wider text-slate-600">
                {t("detail.base_url_label")}
              </FormLabel>
              <FormControl>
                <Input {...field} className="mt-1" />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div>
          <FormLabel className="text-xs uppercase tracking-wider text-slate-600">
            {t("detail.api_key_id_label")}
          </FormLabel>
          <div className="mt-1 flex items-center gap-2">
            <Input
              value={vault.api_key_id}
              disabled
              className="flex-1 font-mono text-slate-400 bg-slate-50"
            />
            <Button type="button" variant="outline" onClick={onReplaceApiKey}>
              {t("detail.replace_key")}
            </Button>
            <Button type="button" variant="outline" onClick={onReveal}>
              {t("detail.reveal_key")}
            </Button>
          </div>
        </div>

        <FormField
          control={form.control}
          name="probe_path"
          render={({ field }) => (
            <FormItem>
              <FormLabel className="text-xs uppercase tracking-wider text-slate-600">
                {t("detail.probe_path_label")}
              </FormLabel>
              <FormControl>
                <Input
                  {...field}
                  placeholder={t("detail.probe_path_placeholder")}
                  className="mt-1"
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <div className="flex items-center justify-between pt-4 border-t border-slate-200">
          <Button
            type="button"
            variant="outline"
            onClick={onRetire}
            className="border-rose-500 text-rose-600 hover:bg-rose-50 hover:text-rose-700"
          >
            {t("detail.retire_vault")}
          </Button>
          <div className="flex gap-2">
            <Button
              type="button"
              variant="outline"
              onClick={() =>
                form.reset({
                  label: vault.label,
                  base_url: vault.base_url,
                  probe_path: vault.probe_path ?? "",
                })
              }
              disabled={!form.formState.isDirty}
            >
              {t("detail.cancel")}
            </Button>
            <Button type="submit" disabled={!form.formState.isDirty || updateMutation.isPending}>
              {t("detail.save")}
            </Button>
          </div>
        </div>
      </form>
    </Form>
  );
}
