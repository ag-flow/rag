import { useTranslation } from "react-i18next";
import { useForm } from "react-hook-form";
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
import { useToast } from "@/hooks/useToast";
import { useAddSource } from "@/hooks/useWorkspaces";

const schema = z.object({
  url: z.string().url("invalid_url"),
  branch: z.string().min(1).default("main"),
  auth_ref: z.string().optional(),
  include: z.string().optional(), // CSV
  exclude: z.string().optional(), // CSV
});

type FormValues = z.infer<typeof schema>;

interface Props {
  name: string;
  open: boolean;
  onOpenChange: (o: boolean) => void;
}

const splitCsv = (s: string | undefined): string[] =>
  (s ?? "")
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);

export function AddSourceDialog({ name, open, onOpenChange }: Props) {
  const { t } = useTranslation("workspace");
  const { toast } = useToast();
  const add = useAddSource(name);
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      url: "",
      branch: "main",
      auth_ref: "",
      include: "",
      exclude: "",
    },
  });

  const onSubmit = (v: FormValues) => {
    add.mutate(
      {
        type: "git",
        config: {
          url: v.url,
          branch: v.branch,
          auth_ref: v.auth_ref || null,
          include: splitCsv(v.include),
          exclude: splitCsv(v.exclude),
        },
      },
      {
        onSuccess: () => {
          toast({ title: t("sources.add.success") });
          form.reset();
          onOpenChange(false);
        },
        onError: () => toast({ title: t("sources.add.error"), variant: "destructive" }),
      },
    );
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t("sources.add.title")}</DialogTitle>
        </DialogHeader>
        <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-3">
          <div>
            <label className="text-xs font-medium text-slate-700">{t("sources.fields.url")}</label>
            <Input {...form.register("url")} placeholder="https://github.com/..." />
            {form.formState.errors.url && (
              <p className="text-xs text-red-600">
                {t(`sources.add.errors.${form.formState.errors.url.message ?? "invalid"}`)}
              </p>
            )}
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.branch")}
            </label>
            <Input {...form.register("branch")} />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.auth_ref")}{" "}
              <span className="text-slate-400">({t("optional")})</span>
            </label>
            <Input {...form.register("auth_ref")} placeholder="github_token" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.include")} <span className="text-slate-400">(csv)</span>
            </label>
            <Input {...form.register("include")} placeholder="**/*.md, docs/**" />
          </div>
          <div>
            <label className="text-xs font-medium text-slate-700">
              {t("sources.fields.exclude")} <span className="text-slate-400">(csv)</span>
            </label>
            <Input {...form.register("exclude")} placeholder="**/node_modules/**" />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
              {t("dialog.cancel")}
            </Button>
            <Button type="submit" disabled={add.isPending}>
              {t("sources.add.submit")}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
