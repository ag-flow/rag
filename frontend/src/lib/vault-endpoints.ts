import { api } from "@/lib/api";
import type { EndpointCreate, EndpointUpdate, VaultEndpoint } from "@/lib/vault-endpoints.types";

const BASE = "/api/admin/harpocrate-vaults";

export const vaultEndpointsApi = {
  list: (vaultId: string) => api.get<VaultEndpoint[]>(`${BASE}/${vaultId}/endpoints`),
  create: (vaultId: string, payload: EndpointCreate) =>
    api.post<VaultEndpoint>(`${BASE}/${vaultId}/endpoints`, payload),
  update: (vaultId: string, endpointId: string, payload: EndpointUpdate) =>
    api.patch<VaultEndpoint>(`${BASE}/${vaultId}/endpoints/${endpointId}`, payload),
  remove: (vaultId: string, endpointId: string) =>
    api.delete<void>(`${BASE}/${vaultId}/endpoints/${endpointId}`),
};
