import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { endpointSharingApi, vaultEndpointsApi } from "@/lib/vault-endpoints";
import type {
  EndpointCreate,
  EndpointSharingUpdate,
  EndpointUpdate,
  UsableEndpoint,
} from "@/lib/vault-endpoints.types";

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

export type UsableEndpointGroup = {
  key: string;
  /** Libellé du coffre ; null pour le groupe « partagés avec moi » (libellé i18n). */
  vaultLabel: string | null;
  endpoints: UsableEndpoint[];
};

/** Groupes du sélecteur de création : un par coffre visible, puis un unique
 * groupe des endpoints partagés par d'autres (leurs coffres ne sont pas à moi). */
export function groupUsableEndpoints(endpoints: UsableEndpoint[]): UsableEndpointGroup[] {
  const groups = new Map<string, UsableEndpointGroup>();
  const shared: UsableEndpoint[] = [];
  for (const ep of endpoints) {
    if (ep.access === "shared") {
      shared.push(ep);
      continue;
    }
    const group = groups.get(ep.vault_id) ?? {
      key: ep.vault_id,
      vaultLabel: ep.vault_label,
      endpoints: [],
    };
    group.endpoints.push(ep);
    groups.set(ep.vault_id, group);
  }
  const result = [...groups.values()];
  if (shared.length > 0) result.push({ key: "shared", vaultLabel: null, endpoints: shared });
  return result;
}

/** Endpoints utilisables pour créer un workspace, groupés pour le sélecteur. */
export function useUsableEndpoints() {
  return useQuery<UsableEndpointGroup[]>({
    queryKey: ["vault-endpoints", "usable"],
    queryFn: async () => groupUsableEndpoints(await endpointSharingApi.usable()),
  });
}

const SHARING_KEY = (endpointId: string) => ["endpoint-sharing", endpointId] as const;

export function useEndpointSharing(vaultId: string, endpointId: string | null) {
  return useQuery({
    queryKey: SHARING_KEY(endpointId ?? ""),
    queryFn: () => vaultEndpointsApi.getSharing(vaultId, endpointId ?? ""),
    enabled: endpointId !== null,
  });
}

export function useSetEndpointSharing(vaultId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ endpointId, payload }: { endpointId: string; payload: EndpointSharingUpdate }) =>
      vaultEndpointsApi.setSharing(vaultId, endpointId, payload),
    onSuccess: (_data, { endpointId }) => {
      void qc.invalidateQueries({ queryKey: SHARING_KEY(endpointId) });
      void qc.invalidateQueries({ queryKey: KEY(vaultId) });
    },
  });
}

export function useFindShareCandidate() {
  return useMutation({ mutationFn: (email: string) => endpointSharingApi.findCandidate(email) });
}

export function useEndpointsHealth(vaultId: string) {
  return useQuery<Record<string, Record<string, string>>>({
    queryKey: ["vault-endpoints-health", vaultId],
    queryFn: () => vaultEndpointsApi.health(vaultId),
    refetchInterval: 15_000,
  });
}
