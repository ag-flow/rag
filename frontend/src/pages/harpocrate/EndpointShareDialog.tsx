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
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import {
  useEndpointSharing,
  useSetEndpointSharing,
  useShareCandidates,
} from "@/hooks/useVaultEndpoints";
import { useToast } from "@/hooks/useToast";
import type { VaultEndpoint } from "@/lib/vault-endpoints.types";

interface Props {
  vaultId: string;
  endpoint: VaultEndpoint | null;
  onOpenChange: (open: boolean) => void;
}

/** Partage d'un endpoint : à tout le monde, sinon à des utilisateurs nommés.
 * Le bénéficiaire peut créer des workspaces avec l'endpoint, jamais le modifier. */
export function EndpointShareDialog({ vaultId, endpoint, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: sharing } = useEndpointSharing(vaultId, endpoint?.id ?? null);
  const { data: candidates = [] } = useShareCandidates(endpoint !== null);
  const saveMutation = useSetEndpointSharing(vaultId);

  const [sharedWithAll, setSharedWithAll] = useState(false);
  const [selected, setSelected] = useState<Set<string>>(new Set());

  // Pré-remplit l'état voulu depuis l'état enregistré, à chaque ouverture.
  useEffect(() => {
    if (!sharing) return;
    setSharedWithAll(sharing.shared_with_all);
    setSelected(new Set(sharing.users.map((u) => u.id)));
  }, [sharing]);

  function toggle(userId: string) {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(userId)) next.delete(userId);
      else next.add(userId);
      return next;
    });
  }

  async function handleSave() {
    if (!endpoint) return;
    try {
      await saveMutation.mutateAsync({
        endpointId: endpoint.id,
        // Partagé à tous : la liste nominative n'a plus d'effet, on ne la garde pas.
        payload: { shared_with_all: sharedWithAll, user_ids: sharedWithAll ? [] : [...selected] },
      });
      toast({ title: t("endpoints.sharing.saved_toast") });
      onOpenChange(false);
    } catch {
      toast({ title: t("endpoints.error_toast"), variant: "destructive" });
    }
  }

  return (
    <Dialog open={endpoint !== null} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[520px]">
        <DialogHeader>
          <DialogTitle>{t("endpoints.sharing.title", { name: endpoint?.label ?? "" })}</DialogTitle>
          <DialogDescription>{t("endpoints.sharing.help")}</DialogDescription>
        </DialogHeader>

        <div className="flex items-center justify-between gap-4 rounded-md border p-3">
          <p className="text-sm font-medium text-slate-800">{t("endpoints.sharing.all")}</p>
          <Switch
            checked={sharedWithAll}
            onCheckedChange={setSharedWithAll}
            aria-label={t("endpoints.sharing.all")}
          />
        </div>

        {!sharedWithAll && (
          <div>
            <p className="mb-2 text-xs uppercase tracking-wider text-slate-600">
              {t("endpoints.sharing.users")}
            </p>
            {candidates.length === 0 ? (
              <p className="text-sm text-slate-500">{t("endpoints.sharing.no_users")}</p>
            ) : (
              <ul className="max-h-64 space-y-1 overflow-y-auto">
                {candidates.map((u) => (
                  <li key={u.id}>
                    <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-slate-50">
                      <input
                        type="checkbox"
                        checked={selected.has(u.id)}
                        onChange={() => toggle(u.id)}
                      />
                      <span className="text-sm text-slate-800">{u.email}</span>
                      {u.username !== u.email && (
                        <span className="text-xs text-slate-400">{u.username}</span>
                      )}
                    </label>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t("endpoints.cancel")}
          </Button>
          <Button
            type="button"
            onClick={() => void handleSave()}
            disabled={!sharing || saveMutation.isPending}
          >
            {t("endpoints.save")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
