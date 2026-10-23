import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";
import type { VaultReconnectPending } from "@/lib/harpocrate-vaults.types";

const ROOT_KEY = ["vaults"] as const;

/** « Reconnecter » : le backend dépose la demande, le navigateur part chez Harpocrate. */
export function useReconnectStart(vaultId: string) {
  return useMutation({ mutationFn: () => harpocrateVaultsApi.reconnectStart(vaultId) });
}

/** Changement de wallet en attente de décision (null : rien à décider). */
export function usePendingReconnect(requestId: string | null) {
  return useQuery<VaultReconnectPending>({
    queryKey: [...ROOT_KEY, "reconnect", requestId],
    queryFn: () => harpocrateVaultsApi.getPendingReconnect(requestId as string),
    enabled: requestId !== null,
    // Une demande résolue ou expirée ne reviendra pas : pas de nouvel essai.
    retry: false,
  });
}

function useInvalidateVault() {
  const qc = useQueryClient();
  return (vaultId: string) => {
    void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId] });
    void qc.invalidateQueries({ queryKey: [...ROOT_KEY, vaultId, "info"] });
  };
}

export function useConfirmReconnect() {
  const invalidate = useInvalidateVault();
  return useMutation({
    mutationFn: (requestId: string) => harpocrateVaultsApi.confirmReconnect(requestId),
    onSuccess: (result) => invalidate(result.vault.id),
  });
}

export function useCancelReconnect() {
  return useMutation({
    mutationFn: (requestId: string) => harpocrateVaultsApi.cancelReconnect(requestId),
  });
}
