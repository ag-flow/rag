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
import {
  useGitCredentialsByHost,
  useSshKeysAll,
} from "@/hooks/useHarpocrateVaults";
import type { Source, SourceCreateRequest, SourceUpdateRequest } from "@/lib/workspaces.types";

// ─── Constantes ────────────────────────────────────────────────────────────

type GitProvider = "github" | "gitlab" | "gitea" | "bitbucket" | "azure-devops";
type AuthType = "token" | "ssh";

const GIT_PROVIDERS: { value: GitProvider; label: string }[] = [
  { value: "github", label: "GitHub" },
  { value: "gitlab", label: "GitLab" },
  { value: "gitea", label: "Gitea" },
  { value: "bitbucket", label: "Bitbucket" },
  { value: "azure-devops", label: "Azure DevOps" },
];

const DEFAULT_SSH_USER: Record<GitProvider, string> = {
  github: "git",
  gitlab: "git",
  gitea: "",
  bitbucket: "git",
  "azure-devops": "",
};

// ─── Schemas ────────────────────────────────────────────────────────────────

const createSchema = z.object({
  source_name: z.string().min(1).regex(/^[a-z0-9_-]+$/, "invalid_slug"),
  url: z.string().min(1, "required"),
  branch: z.string().optional(),
  git_provider: z.string().min(1, "required"),
  auth_type: z.enum(["token", "ssh"]),
  credential_ref: z.string().optional(),
  ssh_username: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

const editSchema = z.object({
  url: z.string().min(1, "required"),
  branch: z.string().optional(),
  git_provider: z.string().optional(),
  auth_type: z.enum(["token", "ssh"]).optional(),
  credential_ref: z.string().optional(),
  ssh_username: z.string().optional(),
  include: z.string().optional(),
  exclude: z.string().optional(),
});

type CreateValues = z.infer<typeof createSchema>;
type EditValues = z.infer<typeof editSchema>;

// ─── Helpers ────────────────────────────────────────────────────────────────

const splitCsv = (s: string | undefined): string[] =>
  (s ?? "").split(",").map((x) => x.trim()).filter(Boolean);

const branchOrUndefined = (b: string | undefined): string | undefined => {
  const trimmed = (b ?? "").trim();
  return trimmed === "" ? undefined : trimmed;
};

// ─── Props ───────────────────────────────────────────────────────────────────

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
  source?: Source;
}

// ─── Composant ───────────────────────────────────────────────────────────────

export function AddSourceDialog({ name, open, onOpenChange, source }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const add = useAddSource(name);
  const update = useUpdateSource(name);
  const testConnection = useTestSourceConnection(name);
  const isEdit = source !== undefined;
  const [testResult, setTestResult] = useState<{
    success: boolean;
    message: string | null;
  } | null>(null);

  // ── Formulaires ──────────────────────────────────────────────────────────

  const createForm = useForm<CreateValues>({
    resolver: zodResolver(createSchema),
    defaultValues: {
      source_name: "",
      url: "",
      branch: "",
      git_provider: "github",
      auth_type: "token",
      credential_ref: "",
      ssh_username: "git",
      include: "",
      exclude: "",
    },
  });

  const editForm = useForm<EditValues>({
    resolver: zodResolver(editSchema),
    defaultValues: {
      url: "",
      branch: "",
      git_provider: "github",
      auth_type: "token",
      credential_ref: "",
      ssh_username: "git",
      include: "",
      exclude: "",
    },
  });

  // Valeurs observées selon le mode actif
  const createProvider = createForm.watch("git_provider") as GitProvider | undefined;
  const createAuthType = createForm.watch("auth_type") as AuthType | undefined;
  const editProvider = editForm.watch("git_provider") as GitProvider | undefined;
  const editAuthType = editForm.watch("auth_type") as AuthType | undefined;

  const watchedProvider = isEdit ? editProvider : createProvider;
  const watchedAuthType = isEdit ? editAuthType : createAuthType;

  // ── Données Harpocrate ───────────────────────────────────────────────────

  const { data: gitTokens = [] } = useGitCredentialsByHost(
    watchedAuthType === "token" && watchedProvider ? watchedProvider : null,
  );
  const { data: sshKeys = [] } = useSshKeysAll();

  // ── Reset à l'ouverture ──────────────────────────────────────────────────

  useEffect(() => {
    if (!open) return;
    setTestResult(null);
    if (isEdit && source) {
      const cfg = source.config as Record<string, unknown>;
      editForm.reset({
        url: (cfg["url"] as string) ?? "",
        branch: (cfg["branch"] as string) ?? "",
        git_provider: (cfg["git_provider"] as GitProvider) ?? "github",
        auth_type: (cfg["auth_type"] as AuthType) ?? "token",
        credential_ref: ((cfg["auth_ref"] as string) ?? (cfg["ssh_key_ref"] as string) ?? ""),
        ssh_username: (cfg["ssh_username"] as string) ?? "git",
        include: ((cfg["include"] as string[]) ?? []).join(", "),
        exclude: ((cfg["exclude"] as string[]) ?? []).join(", "),
      });
    } else {
      createForm.reset({
        source_name: "",
        url: "",
        branch: "",
        git_provider: "github",
        auth_type: "token",
        credential_ref: "",
        ssh_username: "git",
        include: "",
        exclude: "",
      });
    }
  }, [open, source, isEdit, createForm, editForm]);

  // Auto ssh_username selon provider
  useEffect(() => {
    if (!watchedProvider || watchedAuthType !== "ssh") return;
    const defaultUser = DEFAULT_SSH_USER[watchedProvider] ?? "";
    if (isEdit) {
      editForm.setValue("ssh_username", defaultUser);
    } else {
      createForm.setValue("ssh_username", defaultUser);
    }
  }, [watchedProvider, watchedAuthType, isEdit, createForm, editForm]);

  // ── Payloads ─────────────────────────────────────────────────────────────

  function buildCreatePayload(v: CreateValues): SourceCreateRequest {
    const branch = branchOrUndefined(v.branch);
    const authRef = v.auth_type === "token" ? (v.credential_ref || undefined) : undefined;
    const sshKeyRef = v.auth_type === "ssh" ? (v.credential_ref || undefined) : undefined;
    const sshUsername = v.auth_type === "ssh" ? (v.ssh_username || undefined) : undefined;
    return {
      name: v.source_name,
      type: "git",
      git_provider: v.git_provider,
      auth_type: v.auth_type,
      ...(authRef !== undefined && { auth_ref: authRef }),
      ...(sshKeyRef !== undefined && { ssh_key_ref: sshKeyRef }),
      ...(sshUsername !== undefined && { ssh_username: sshUsername }),
      config: {
        url: v.url,
        ...(branch !== undefined && { branch }),
        include: splitCsv(v.include),
        exclude: splitCsv(v.exclude),
      },
    };
  }

  function buildUpdatePayload(v: EditValues): SourceUpdateRequest {
    const branch = branchOrUndefined(v.branch);
    const authRef = v.auth_type === "token" ? (v.credential_ref || undefined) : undefined;
    const sshKeyRef = v.auth_type === "ssh" ? (v.credential_ref || undefined) : undefined;
    const sshUsername = v.auth_type === "ssh" ? (v.ssh_username || undefined) : undefined;
    return {
      ...(v.git_provider !== undefined && { git_provider: v.git_provider }),
      ...(v.auth_type !== undefined && { auth_type: v.auth_type }),
      ...(authRef !== undefined && { auth_ref: authRef }),
      ...(sshKeyRef !== undefined && { ssh_key_ref: sshKeyRef }),
      ...(sshUsername !== undefined && { ssh_username: sshUsername }),
      config: {
        url: v.url,
        ...(branch !== undefined && { branch }),
        include: splitCsv(v.include),
        exclude: splitCsv(v.exclude),
      },
    };
  }

  // ── Handlers ─────────────────────────────────────────────────────────────

  const onSubmitCreate = (v: CreateValues) => {
    add.mutate(buildCreatePayload(v), {
      onSuccess: (created) => {
        if (created.branch_warning) {
          toast({ title: t("sources.add.branch_warning") });
        }
        toast({ title: t("sources.add.success") });
        createForm.reset();
        onOpenChange(false);
      },
      onError: () => toast({ title: t("sources.add.error"), variant: "destructive" }),
    });
  };

  const onSubmitEdit = (v: EditValues) => _saveEdit(v, { andThen: "close" });

  const _saveEdit = (v: EditValues, opts: { andThen: "close" | "test" }) => {
    update.mutate(
      { sourceId: source!.id, payload: buildUpdatePayload(v) },
      {
        onSuccess: () => {
          if (opts.andThen === "close") {
            toast({ title: t("sources.edit.success") });
            onOpenChange(false);
          } else {
            setTestResult(null);
            testConnection.mutate(source!.id, {
              onSuccess: (r) => setTestResult(r),
              onError: () =>
                setTestResult({ success: false, message: t("sources.test.error") }),
            });
          }
        },
        onError: () => toast({ title: t("sources.edit.error"), variant: "destructive" }),
      },
    );
  };

  // ── Dérivées UI ──────────────────────────────────────────────────────────

  const isPending = isEdit ? update.isPending : add.isPending;
  const title = isEdit ? t("sources.edit.title") : t("sources.add.title");
  const submitLabel = isEdit ? t("sources.edit.submit") : t("sources.add.submit");

  const credentialItems =
    watchedAuthType === "ssh"
      ? sshKeys.map((k) => ({
          value: k.harpo_path,
          label: k.name,
          sub: `${k.vault_label} · ${k.key_id} (${k.key_type})`,
        }))
      : gitTokens.map((g) => ({
          value: g.harpo_path,
          label: g.label,
          sub: `${g.vault_label} · ${g.key_id}`,
        }));

  // ── Render ───────────────────────────────────────────────────────────────

  if (isEdit) {
    const { register, handleSubmit, formState, control } = editForm;
    return (
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
          </DialogHeader>
          <form onSubmit={handleSubmit(onSubmitEdit)} className="space-y-3">
            {/* Source name (lecture seule en édition) */}
            {source?.name && (
              <div>
                <label className="text-xs font-medium text-slate-700">
                  {t("sources.fields.source_name")}
                </label>
                <Input value={source.name} readOnly disabled className="bg-slate-50 opacity-70" />
              </div>
            )}

            {/* Branche */}
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.branch")}
              </label>
              <Input
                {...register("branch")}
                placeholder={t("sources.fields.branch_placeholder")}
              />
            </div>

            {/* Bloc auth */}
            <AuthBlock
              control={control}
              register={register}
              watchedAuthType={watchedAuthType}
              credentialItems={credentialItems}
              t={t}
            />

            {/* URL — après le provider pour guider le format (HTTPS ou SSH) */}
            <div>
              <label className="text-xs font-medium text-slate-700">
                {t("sources.fields.url")}
              </label>
              <Input {...register("url")} placeholder="https://github.com/org/repo.git" />
              {formState.errors.url && (
                <p className="text-xs text-red-600">
                  {t(`sources.add.errors.${formState.errors.url.message ?? "invalid"}`)}
                </p>
              )}
            </div>

            {/* Include / Exclude */}
            <IncludeExclude register={register} t={t} />

            {/* Résultat test */}
            {testResult !== null && (
              <TestResultBanner testResult={testResult} t={t} />
            )}

            <DialogFooter className="gap-2">
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
                {t("dialog.cancel")}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={update.isPending || testConnection.isPending}
                onClick={handleSubmit((v) => _saveEdit(v, { andThen: "test" }))}
              >
                {update.isPending || testConnection.isPending
                  ? t("sources.test.testing")
                  : t("sources.test.button")}
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

  // Mode création
  const { register, handleSubmit, formState, control } = createForm;
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[500px] max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
        </DialogHeader>
        <form onSubmit={handleSubmit(onSubmitCreate)} className="space-y-3">
          {/* Source name */}
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
            <p className="text-xs text-slate-400 mt-0.5">
              {t("sources.fields.source_name_hint")}
            </p>
          </div>

          {/* Branche */}
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.branch")}
            </label>
            <Input
              {...register("branch")}
              placeholder={t("sources.fields.branch_placeholder")}
            />
          </div>

          {/* Bloc auth */}
          <AuthBlock
            control={control}
            register={register}
            watchedAuthType={watchedAuthType}
            credentialItems={credentialItems}
            t={t}
          />

          {/* URL — après le provider pour guider le format (HTTPS ou SSH) */}
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.url")}
            </label>
            <Input {...register("url")} placeholder="https://github.com/org/repo.git" />
            {formState.errors.url && (
              <p className="text-xs text-red-600">
                {t(`sources.add.errors.${formState.errors.url.message ?? "invalid"}`)}
              </p>
            )}
          </div>

          {/* Include / Exclude */}
          <IncludeExclude register={register} t={t} />

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

// ─── Sous-composants ─────────────────────────────────────────────────────────

interface AuthBlockProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  control: any;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  register: any;
  watchedAuthType: AuthType | undefined;
  credentialItems: { value: string; label: string; sub: string }[];
  t: (key: string) => string;
}

function AuthBlock({ control, register, watchedAuthType, credentialItems, t }: AuthBlockProps) {
  return (
    <div className="rounded-md border bg-slate-50 p-3 space-y-3">
      {/* Provider */}
      <div>
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.git_provider")}
        </label>
        <Controller
          name="git_provider"
          control={control}
          render={({ field }) => (
            <Select value={(field.value as string) ?? ""} onValueChange={field.onChange}>
              <SelectTrigger className="mt-1">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {GIT_PROVIDERS.map((p) => (
                  <SelectItem key={p.value} value={p.value}>
                    {p.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        />
      </div>

      {/* Auth type */}
      <div>
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.auth_type")}
        </label>
        <Controller
          name="auth_type"
          control={control}
          render={({ field }) => (
            <div className="flex gap-4 mt-1">
              {(["token", "ssh"] as AuthType[]).map((at) => (
                <label key={at} className="flex items-center gap-2 text-sm cursor-pointer">
                  <input
                    type="radio"
                    value={at}
                    checked={field.value === at}
                    onChange={() => field.onChange(at)}
                  />
                  {at === "token"
                    ? t("sources.fields.auth_type_token")
                    : t("sources.fields.auth_type_ssh")}
                </label>
              ))}
            </div>
          )}
        />
      </div>

      {/* Credential select */}
      <div>
        <label className="text-xs font-medium text-slate-700">
          {t("sources.fields.credential")}
        </label>
        <Controller
          name="credential_ref"
          control={control}
          render={({ field }) =>
            credentialItems.length === 0 ? (
              <p className="text-xs text-amber-600 mt-1">
                {t("sources.fields.credential_none")}
              </p>
            ) : (
              <Select value={(field.value as string) ?? ""} onValueChange={field.onChange}>
                <SelectTrigger className="mt-1">
                  <SelectValue placeholder={t("sources.fields.credential_placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  {credentialItems.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      <span className="font-medium">{item.label}</span>
                      <span className="ml-2 text-xs text-slate-400">{item.sub}</span>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )
          }
        />
      </div>

      {/* SSH username (conditionnel) */}
      {watchedAuthType === "ssh" && (
        <div>
          <label className="text-xs font-medium text-slate-700">
            {t("sources.fields.ssh_username")}
          </label>
          <Input
            {...register("ssh_username")}
            placeholder={t("sources.fields.ssh_username_placeholder")}
            className="mt-1"
          />
        </div>
      )}
    </div>
  );
}

interface IncludeExcludeProps {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  register: any;
  t: (key: string) => string;
}

function IncludeExclude({ register, t }: IncludeExcludeProps) {
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

interface TestResultBannerProps {
  testResult: { success: boolean; message: string | null };
  t: (key: string) => string;
}

function TestResultBanner({ testResult, t }: TestResultBannerProps) {
  return (
    <p
      className={`text-xs px-2 py-1 rounded ${
        testResult.success ? "bg-green-50 text-green-700" : "bg-red-50 text-red-700"
      }`}
    >
      {testResult.success
        ? t("sources.test.success")
        : `${t("sources.test.failure")} ${testResult.message ?? ""}`}
    </p>
  );
}
