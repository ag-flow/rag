import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { harpocrateVaultsApi } from "@/lib/harpocrate-vaults";
import { vaultEndpointsApi } from "@/lib/vault-endpoints";
import type { EndpointCreate, EndpointUpdate, VaultEndpoint } from "@/lib/vault-endpoints.types";
import type { VaultSummary } from "@/lib/harpocrate-vaults.types";

const KEY = (vaultId: string) => ["vault-endpoints", vaultId] as const;

export function useVaultEndpoints(vaultId: string) {
  return useQuery({
    queryKey: KEY(vaultId),
    queryFn: () => vaultEndpointsApi.list(vaultId),
  });
}

export function useCreateEndpoint(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: EndpointCreate) => vaultEndpointsApi.create(vaultId, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(vaultId) }),
  });
}

export function useUpdateEndpoint(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ endpointId, payload }: { endpointId: string; payload: EndpointUpdate }) =>
      vaultEndpointsApi.update(vaultId, endpointId, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(vaultId) }),
  });
}

export function useDeleteEndpoint(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (endpointId: string) => vaultEndpointsApi.remove(vaultId, endpointId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(vaultId) }),
  });
}

export type VaultWithEndpoints = {
  vault: VaultSummary;
  endpoints: VaultEndpoint[];
};

/** Tous les endpoints, groupés par coffre — pour le sélecteur de création de workspace. */
export function useAllVaultEndpoints() {
  return useQuery<VaultWithEndpoints[]>({
    queryKey: ["vault-endpoints", "all"],
    queryFn: async () => {
      const vaults = await harpocrateVaultsApi.list();
      const grouped = await Promise.all(
        vaults.map(async (vault) => ({
          vault,
          endpoints: await vaultEndpointsApi.list(vault.id),
        })),
      );
      return grouped.filter((g) => g.endpoints.length > 0);
    },
  });
}
