import { api } from "@/lib/api";
import type { EndpointCreate, EndpointUpdate, VaultEndpoint } from "@/lib/vault-endpoints.types";

/** Test réel de la config saisie (avant Save) : embedding « ping » + rerank. */
export type EndpointTestRequest = {
  indexer: { provider: string; model: string; api_key_ref?: string | null; base_url?: string | null };
  rerank?: {
    provider: string;
    model: string;
    api_key_ref?: string | null;
    base_url?: string | null;
  } | null;
};

export type EndpointTestResult = {
  vectorization: { ok: boolean; message: string };
  rerank: { ok: boolean; message: string } | null;
};

const BASE = "/api/admin/harpocrate-vaults";

export const vaultEndpointsApi = {
  list: (vaultId: string) => api.get<VaultEndpoint[]>(`${BASE}/${vaultId}/endpoints`),
  create: (vaultId: string, payload: EndpointCreate) =>
    api.post<VaultEndpoint>(`${BASE}/${vaultId}/endpoints`, payload),
  update: (vaultId: string, endpointId: string, payload: EndpointUpdate) =>
    api.patch<VaultEndpoint>(`${BASE}/${vaultId}/endpoints/${endpointId}`, payload),
  remove: (vaultId: string, endpointId: string) =>
    api.delete<void>(`${BASE}/${vaultId}/endpoints/${endpointId}`),
  test: (vaultId: string, payload: EndpointTestRequest) =>
    api.post<EndpointTestResult>(`${BASE}/${vaultId}/endpoints/test`, payload),
};
