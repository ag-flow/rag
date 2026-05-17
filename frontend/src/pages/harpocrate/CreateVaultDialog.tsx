import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useTranslation } from "react-i18next";
import { AlertCircle } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
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
import { Label } from "@/components/ui/label";
import { useCreateVault } from "@/hooks/useHarpocrateVaults";
import { vaultCreateSchema, type VaultCreateForm } from "@/lib/validators";
import { ApiError } from "@/lib/api";
import { useToast } from "@/hooks/useToast";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

interface CreateVaultDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (vault: VaultSummary) => void;
}

export function CreateVaultDialog({
  open,
  onOpenChange,
  onCreated,
}: CreateVaultDialogProps) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const createMutation = useCreateVault();
  const [dekMissing, setDekMissing] = useState(false);
  const [nameError, setNameError] = useState<string | null>(null);

  const form = useForm<VaultCreateForm>({
    resolver: zodResolver(vaultCreateSchema),
    defaultValues: {
      name: "",
      label: "",
      base_url: "",
      api_key_id: "",
      api_key: "",
      probe_path: "",
      is_default: true,
    },
  });

  function handleClose(nextOpen: boolean) {
    onOpenChange(nextOpen);
    if (!nextOpen) {
      // Reset state à la fermeture.
      setDekMissing(false);
      setNameError(null);
      form.reset();
    }
  }

  async function onSubmit(values: VaultCreateForm) {
    setNameError(null);
    setDekMissing(false);
    try {
      const created = await createMutation.mutateAsync({
        name: values.name,
        label: values.label,
        base_url: values.base_url,
        api_key_id: values.api_key_id,
        api_key: values.api_key,
        probe_path: values.probe_path === "" ? null : values.probe_path,
        is_default: values.is_default,
      });
      toast({ title: t("create_dialog.created_toast", { name: created.name }) });
      handleClose(false);
      onCreated(created);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 503) {
          setDekMissing(true);
          return;
        }
        if (err.status === 409) {
          setNameError(t("create_dialog.name_taken"));
          return;
        }
        // 422 et autres : message global.
      }
      toast({
        title: t("create_dialog.generic_error"),
        variant: "destructive",
      });
    }
  }

  return (
    <Dialog open={open} onOpenChange={handleClose}>
      <DialogContent className="sm:max-w-[480px]">
        {dekMissing ? (
          <DekMissingPanel onClose={() => handleClose(false)} />
        ) : (
          <>
            <DialogHeader>
              <DialogTitle>{t("create_dialog.title")}</DialogTitle>
              <DialogDescription>{t("create_dialog.subtitle")}</DialogDescription>
            </DialogHeader>

            <Form {...form}>
              <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("create_dialog.name_label")}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={t("create_dialog.name_placeholder")}
                          className="font-mono"
                        />
                      </FormControl>
                      <FormDescription className="text-xs">
                        {t("create_dialog.name_help")}
                      </FormDescription>
                      {nameError && (
                        <p className="text-sm font-medium text-rose-600">{nameError}</p>
                      )}
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="label"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("create_dialog.label_label")}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={t("create_dialog.label_placeholder")}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="base_url"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>{t("create_dialog.base_url_label")}</FormLabel>
                      <FormControl>
                        <Input
                          {...field}
                          placeholder={t("create_dialog.base_url_placeholder")}
                        />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <div className="grid grid-cols-3 gap-3">
                  <FormField
                    control={form.control}
                    name="api_key_id"
                    render={({ field }) => (
                      <FormItem className="col-span-1">
                        <FormLabel>{t("create_dialog.api_key_id_label")}</FormLabel>
                        <FormControl>
                          <Input
                            {...field}
                            placeholder={t("create_dialog.api_key_id_placeholder")}
                            className="font-mono"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                  <FormField
                    control={form.control}
                    name="api_key"
                    render={({ field }) => (
                      <FormItem className="col-span-2">
                        <FormLabel>{t("create_dialog.api_key_label")}</FormLabel>
                        <FormControl>
                          <Input
                            type="password"
                            {...field}
                            placeholder={t("create_dialog.api_key_placeholder")}
                            className="font-mono"
                          />
                        </FormControl>
                        <FormMessage />
                      </FormItem>
                    )}
                  />
                </div>

                <FormField
                  control={form.control}
                  name="is_default"
                  render={({ field }) => (
                    <FormItem className="flex flex-row items-center gap-3 rounded bg-slate-50 p-2.5">
                      <FormControl>
                        <input
                          type="checkbox"
                          checked={field.value}
                          onChange={(e) => field.onChange(e.target.checked)}
                          className="m-0"
                        />
                      </FormControl>
                      <Label className="text-sm m-0 cursor-pointer">
                        {t("create_dialog.set_default_label")}
                      </Label>
                    </FormItem>
                  )}
                />

                <DialogFooter>
                  <Button
                    type="button"
                    variant="outline"
                    onClick={() => handleClose(false)}
                  >
                    {t("create_dialog.cancel")}
                  </Button>
                  <Button type="submit" disabled={createMutation.isPending}>
                    {t("create_dialog.submit")}
                  </Button>
                </DialogFooter>
              </form>
            </Form>
          </>
        )}
      </DialogContent>
    </Dialog>
  );
}

function DekMissingPanel({ onClose }: { onClose: () => void }) {
  const { t } = useTranslation("harpocrate");
  return (
    <>
      <DialogHeader>
        <div className="flex items-center gap-3">
          <AlertCircle className="h-6 w-6 text-rose-600" />
          <DialogTitle className="text-rose-700">
            {t("create_dialog.dek_missing_title")}
          </DialogTitle>
        </div>
      </DialogHeader>
      <DialogDescription className="text-sm leading-relaxed">
        {t("create_dialog.dek_missing_body")}
      </DialogDescription>
      <DialogFooter>
        <Button variant="outline" onClick={onClose}>
          {t("create_dialog.dek_missing_close")}
        </Button>
      </DialogFooter>
    </>
  );
}
