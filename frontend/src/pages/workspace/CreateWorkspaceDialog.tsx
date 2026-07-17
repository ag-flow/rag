import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
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
  SelectGroup,
  SelectItem,
  SelectLabel,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateWorkspace } from "@/hooks/useWorkspaces";
import { useAllVaultEndpoints } from "@/hooks/useVaultEndpoints";
import { useToast } from "@/hooks/useToast";

const NAME_RE = /^[a-z][a-z0-9_-]{0,62}$/;

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated?: (ws: { name: string }) => void;
}

/** Création de workspace : nom + choix d'un endpoint (préréglage du coffre).
 *
 * La vectorisation ne se configure plus champ par champ ici — elle vit dans
 * l'onglet Endpoints du coffre, et sa config est copiée à la création
 * (snapshot).
 */
export function CreateWorkspaceDialog({ open, onOpenChange, onCreated }: Props) {
  const { t } = useTranslation("workspaces");
  const { toast } = useToast();
  const createMutation = useCreateWorkspace();
  const { data: grouped = [], isLoading } = useAllVaultEndpoints();

  const [name, setName] = useState("");
  const [endpointId, setEndpointId] = useState<string>("");

  useEffect(() => {
    if (!open) return;
    setName("");
    // Pré-sélectionne l'unique endpoint s'il n'y en a qu'un.
    const all = grouped.flatMap((g) => g.endpoints);
    setEndpointId(all.length === 1 && all[0] ? all[0].id : "");
  }, [open, grouped]);

  const hasEndpoints = grouped.some((g) => g.endpoints.length > 0);
  const nameValid = NAME_RE.test(name);
  const canSubmit = nameValid && endpointId !== "" && !createMutation.isPending;

  const selected = grouped.flatMap((g) => g.endpoints).find((ep) => ep.id === endpointId);

  async function handleSubmit() {
    try {
      const resp = await createMutation.mutateAsync({ name, endpoint_id: endpointId });
      toast({ title: t("toasts.created", { name: resp.name }) });
      onOpenChange(false);
      onCreated?.({ name: resp.name });
    } catch {
      toast({ title: t("common:errors.generic"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[480px]">
        <DialogHeader>
          <DialogTitle>{t("create")}</DialogTitle>
          <DialogDescription>{t("form.endpoint_intro")}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("form.name")}
            </Label>
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="mon-projet"
              className="mt-1 font-mono"
              autoFocus
            />
            <p className="mt-1 text-xs text-slate-500">{t("form.name_help")}</p>
          </div>

          <div>
            <Label className="text-xs uppercase tracking-wider text-slate-600">
              {t("form.endpoint")}
            </Label>
            {isLoading ? (
              <p className="mt-1 text-sm text-slate-500">…</p>
            ) : !hasEndpoints ? (
              <div className="mt-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
                <p className="text-sm text-amber-900">{t("form.endpoint_none")}</p>
                <Button asChild variant="outline" size="sm" className="mt-2">
                  <Link to="/settings/harpocrate-vaults">{t("form.endpoint_none_link")}</Link>
                </Button>
              </div>
            ) : (
              <Select value={endpointId} onValueChange={setEndpointId}>
                <SelectTrigger className="mt-1" aria-label={t("form.endpoint")}>
                  <SelectValue placeholder={t("form.endpoint_placeholder")} />
                </SelectTrigger>
                <SelectContent>
                  {grouped.map((g) => (
                    <SelectGroup key={g.vault.id}>
                      <SelectLabel>{g.vault.label}</SelectLabel>
                      {g.endpoints.map((ep) => (
                        <SelectItem key={ep.id} value={ep.id}>
                          {ep.label} — {ep.indexer.provider}/{ep.indexer.model}
                        </SelectItem>
                      ))}
                    </SelectGroup>
                  ))}
                </SelectContent>
              </Select>
            )}
            {selected && (
              <p className="mt-1 text-xs text-slate-500">
                {selected.rerank
                  ? t("form.endpoint_with_rerank", {
                      rerank: `${selected.rerank.provider}/${selected.rerank.model}`,
                    })
                  : t("form.endpoint_no_rerank")}
              </p>
            )}
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("form.cancel")}
          </Button>
          <Button type="button" onClick={() => void handleSubmit()} disabled={!canSubmit}>
            {t("form.submit")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
