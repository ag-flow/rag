import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Dialog,
  DialogContent,
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
import { useToast } from "@/hooks/useToast";
import { useAddSource, useUpdateSource, useTestSourceConnection } from "@/hooks/useWorkspaces";
import { useVaults } from "@/hooks/useHarpocrateVaults";
import type { Source } from "@/lib/workspaces.types";

const createSchema = z.object({
  source_name: z.string().min(1).regex(/^[a-z0-9_-]+$/, "invalid_slug"),
  vault: z.string().min(1, "required"),
  url: z.string().url("invalid_url"),
  branch: z.string().min(1).default("main"),
  auth_value: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

const editSchema = z.object({
  vault: z.string().optional(),
  url: z.string().url("invalid_url"),
  branch: z.string().min(1).default("main"),
  auth_value: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

type CreateValues = z.infer<typeof createSchema>;
type EditValues = z.infer<typeof editSchema>;

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  source?: Source;
}

const splitCsv = (s: string | undefined): string[] =>
  (s ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

export function AddSourceDialog({ name, open, onOpenChange, source }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const add = useAddSource(name);
  const update = useUpdateSource(name);
  const testConnection = useTestSourceConnection(name);
  const isEdit = source !== undefined;
  const { data: vaults } = useVaults();
  const [testResult, setTestResult] = useState<{ success: boolean; message: string | null } | null>(
    null,
  );

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      source_name: "",
      vault: "",
      url: "",
      branch: "main",
      auth_value: "",
      include: "",
      exclude: "",
    },
  });

  const editForm = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      url: "",
      branch: "main",
      auth_value: "",
      include: "",
      exclude: "",
    },
  });

  useEffect(() => {
    if (!open) return;
    setTestResult(null);
    const firstVault = vaults?.[0];
    if (isEdit && source) {
      editForm.reset({
        vault: firstVault?.name ?? "",
        url: source.config.url,
        branch: source.config.branch,
        auth_value: "",
        include: source.config.include.join(", "),
        exclude: source.config.exclude.join(", "),
      });
    } else {
      createForm.reset({
        source_name: "",
        vault: firstVault?.name ?? "",
        url: "",
        branch: "main",
        auth_value: "",
        include: "",
        exclude: "",
      });
    }
  }, [open, source, isEdit, vaults, createForm, editForm]);

  const onSubmitCreate = (v: CreateValues) => {
    add.mutate(
      {
        name: v.source_name,
        type: "git",
        api_key_vault: v.vault,
        auth_value: v.auth_value || null,
        config: {
          url: v.url,
          branch: v.branch,
          include: splitCsv(v.include),
          exclude: splitCsv(v.exclude),
        },
      },
      {
        onSuccess: () => {
          toast({ title: t("sources.add.success") });
          createForm.reset();
          onOpenChange(false);
        },
        onError: () => toast({ title: t("sources.add.error"), variant: "destructive" }),
      },
    );
  };

  const onSubmitEdit = (v: EditValues) => {
    update.mutate(
      {
        sourceId: source!.id,
        payload: {
          api_key_vault: v.vault || null,
          auth_value: v.auth_value || null,
          config: {
            url: v.url,
            branch: v.branch,
            include: splitCsv(v.include),
            exclude: splitCsv(v.exclude),
          },
        },
      },
      {
        onSuccess: () => {
          toast({ title: t("sources.edit.success") });
          onOpenChange(false);
        },
        onError: () => toast({ title: t("sources.edit.error"), variant: "destructive" }),
      },
    );
  };

  const isPending = isEdit ? update.isPending : add.isPending;
  const title = isEdit ? t("sources.edit.title") : t("sources.add.title");
  const submitLabel = isEdit ? t("sources.edit.submit") : t("sources.add.submit");

  if (isEdit) {
    const { register, handleSubmit, formState, control } = editForm;
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmitEdit)} className="space-y-3">
            {source?.name && (
              <div>
                <label className="text-xs font-medium text-slate-700">
                  {t("sources.fields.source_name")}
                </label>
                <Input value={source.name} readOnly disabled className="bg-slate-50 opacity-70" />
              </div>
            )}
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.vault")}
              </label>
              <Controller
                name="vault"
                control={control}
                render={({ field }) => (
                  <Select value={field.value ?? ""} onValueChange={field.onChange}>
                    <SelectTrigger>
                      <SelectValue placeholder={t("sources.fields.vault_placeholder")} />
                    </SelectTrigger>
                    <SelectContent>
                      {(vaults ?? []).map((v) => (
                        <SelectItem key={v.name} value={v.name}>
                          {v.label || v.name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                )}
              />
            </div>
            <UrlField register={register} errors={formState.errors} t={t} />
            <BranchField register={register} t={t} />
            <AuthValueField register={register} control={control} t={t} />
            <IncludeExcludeFields register={register} t={t} />
            {testResult !== null && (
              <p
                className={`text-xs px-2 py-1 rounded ${
                  testResult.success
                    ? "bg-green-50 text-green-700"
                    : "bg-red-50 text-red-700"
                }`}
              >
                {testResult.success
                  ? t("sources.test.success")
                  : `${t("sources.test.failure")} ${testResult.message ?? ""}`}
              </p>
            )}
            <DialogFooter className="gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {t("dialog.cancel")}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={testConnection.isPending}
                onClick={() => {
                  if (!source) return;
                  setTestResult(null);
                  testConnection.mutate(source.id, {
                    onSuccess: (r) => setTestResult(r),
                    onError: () =>
                      setTestResult({ success: false, message: t("sources.test.error") }),
                  });
                }}
              >
                {testConnection.isPending ? t("sources.test.testing") : t("sources.test.button")}
              </Button>
              <Button type="submit" disabled={isPending}>
                {submitLabel}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    );
  }

  const { register, handleSubmit, formState, control } = createForm;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmitCreate)} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.source_name")}
            </label>
            <Input
              {...register("source_name")}
              placeholder={t("sources.fields.source_name_placeholder")}
            />
            {formState.errors.source_name && (
              <p className="text-xs text-red-600">
                {t(
                  `sources.add.errors.${formState.errors.source_name.message ?? "invalid"}`,
                  t("sources.fields.source_name_hint"),
                )}
              </p>
            )}
            <p className="text-xs text-slate-400 mt-0.5">{t("sources.fields.source_name_hint")}</p>
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.vault")}
            </label>
            <Controller
              name="vault"
              control={control}
              render={({ field }) => (
                <Select value={field.value} onValueChange={field.onChange}>
                  <SelectTrigger>
                    <SelectValue placeholder={t("sources.fields.vault_placeholder")} />
                  </SelectTrigger>
                  <SelectContent>
                    {(vaults ?? []).map((v) => (
                      <SelectItem key={v.name} value={v.name}>
                        {v.label || v.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            />
            {formState.errors.vault && (
              <p className="text-xs text-red-600">{t("sources.add.errors.required")}</p>
            )}
          </div>
          <UrlField register={register} errors={formState.errors} t={t} />
          <BranchField register={register} t={t} />
          <AuthValueField register={register} control={control} t={t} />
          <IncludeExcludeFields register={register} t={t} />
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("dialog.cancel")}
            </Button>
            <Button type="submit" disabled={isPending}>
              {submitLabel}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

// ─── Sub-components (shared between create and edit) ───────────────────────

type FieldProps = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  register: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  errors?: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control?: any;
  t: (key: string) => string;
};

function UrlField({ register, errors, t }: FieldProps) {
  return (
    <div>
      <label className="text-xs font-medium text-slate-700">{t("sources.fields.url")}</label>
      <Input {...register("url")} placeholder="https://github.com/..." />
      {errors?.url && (
        <p className="text-xs text-red-600">
          {t(`sources.add.errors.${errors.url.message ?? "invalid"}`)}
        </p>
      )}
    </div>
  );
}

function BranchField({ register, t }: FieldProps) {
  return (
    <div>
      <label className="text-xs font-medium text-slate-700">{t("sources.fields.branch")}</label>
      <Input {...register("branch")} />
    </div>
  );
}

function AuthValueField({ register, t }: FieldProps) {
  return (
    <div>
      <div className="flex items-baseline justify-between">
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.auth_value")}{" "}
          <span className="text-slate-400">({t("optional")})</span>
        </label>
        <a
          href="https://github.com/settings/tokens/new"
          target="_blank"
          rel="noopener noreferrer"
          className="text-xs text-blue-600 hover:underline"
        >
          {t("sources.fields.auth_value_link")}
        </a>
      </div>
      <Input
        {...register("auth_value")}
        type="password"
        placeholder={t("sources.fields.auth_value_placeholder")}
        autoComplete="off"
      />
    </div>
  );
}

function IncludeExcludeFields({ register, t }: FieldProps) {
  return (
    <>
      <div>
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.include")} <span className="text-slate-400">(csv)</span>
        </label>
        <Input {...register("include")} placeholder="**/*.md, docs/**" />
      </div>
      <div>
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.exclude")} <span className="text-slate-400">(csv)</span>
        </label>
        <Input {...register("exclude")} placeholder="**/node_modules/**" />
      </div>
    </>
  );
}
