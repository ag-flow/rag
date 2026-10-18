import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Switch } from "@/components/ui/switch";
import {
  useEndpointSharing,
  useFindShareCandidate,
  useSetEndpointSharing,
} from "@/hooks/useVaultEndpoints";
import { useToast } from "@/hooks/useToast";
import type { ShareUser, VaultEndpoint } from "@/lib/vault-endpoints.types";

interface Props {
  vaultId: string;
  endpoint: VaultEndpoint | null;
  onOpenChange: (open: boolean) => void;
}

/** Partage d'un endpoint : à tout le monde, sinon à des utilisateurs nommés.
 * Le bénéficiaire peut créer des workspaces avec l'endpoint, jamais le modifier.
 * On le désigne par son email EXACT : l'application ne liste pas ses comptes. */
export function EndpointShareDialog({ vaultId, endpoint, onOpenChange }: Props) {
  const { t } = useTranslation("harpocrate");
  const { toast } = useToast();
  const { data: sharing } = useEndpointSharing(vaultId, endpoint?.id ?? null);
  const findMutation = useFindShareCandidate();
  const saveMutation = useSetEndpointSharing(vaultId);

  const [sharedWithAll, setSharedWithAll] = useState(false);
  const [users, setUsers] = useState<ShareUser[]>([]);
  const [email, setEmail] = useState("");
  const [lookupError, setLookupError] = useState<string | null>(null);

  // Pré-remplit l'état voulu depuis l'état enregistré.
  useEffect(() => {
    if (!sharing) return;
    setSharedWithAll(sharing.shared_with_all);
    setUsers(sharing.users);
  }, [sharing]);

  async function handleAdd() {
    setLookupError(null);
    try {
      const user = await findMutation.mutateAsync(email.trim());
      setUsers((prev) => (prev.some((u) => u.id === user.id) ? prev : [...prev, user]));
      setEmail("");
    } catch {
      setLookupError(t("endpoints.sharing.user_not_found"));
    }
  }

  async function handleSave() {
    if (!endpoint) return;
    try {
      await saveMutation.mutateAsync({
        endpointId: endpoint.id,
        // Partagé à tous : la liste nominative n'a plus d'effet, on ne la garde pas.
        payload: {
          shared_with_all: sharedWithAll,
          user_ids: sharedWithAll ? [] : users.map((u) => u.id),
        },
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
          <div className="space-y-2">
            <p className="text-xs uppercase tracking-wider text-slate-600">
              {t("endpoints.sharing.users")}
            </p>
            <div className="flex gap-2">
              <Input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder={t("endpoints.sharing.email_placeholder")}
                aria-label={t("endpoints.sharing.email_placeholder")}
              />
              <Button
                type="button"
                variant="outline"
                onClick={() => void handleAdd()}
                disabled={email.trim() === "" || findMutation.isPending}
              >
                {t("endpoints.sharing.add")}
              </Button>
            </div>
            {lookupError && <p className="text-xs text-amber-600">{lookupError}</p>}
            {users.length === 0 ? (
              <p className="text-sm text-slate-500">{t("endpoints.sharing.no_users")}</p>
            ) : (
              <ul className="space-y-1">
                {users.map((u) => (
                  <li key={u.id} className="flex items-center justify-between rounded px-2 py-1">
                    <span className="text-sm text-slate-800">{u.email}</span>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => setUsers((prev) => prev.filter((x) => x.id !== u.id))}
                      aria-label={t("endpoints.sharing.remove", { email: u.email })}
                    >
                      <X className="h-4 w-4" />
                    </Button>
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
