import { api } from "@/lib/api";
import type {
  SecretListResponse,
  SecretTypeSummary,
  VaultCreateRequest,
  VaultRevealApiKeyResponse,
  VaultRotateApiKeyRequest,
  VaultSummary,
  VaultTestConnectionResult,
  VaultUpdateRequest,
  WalletInfoResponse,
} from "@/lib/harpocrate-vaults.types";

const BASE = "/api/admin/harpocrate-vaults";

export const harpocrateVaultsApi = {
  list: () => api.get<VaultSummary[]>(BASE),

  get: (id: string) => api.get<VaultSummary>(`${BASE}/${id}`),

  create: (payload: VaultCreateRequest) =>
    api.post<VaultSummary>(BASE, payload),

  update: (id: string, payload: VaultUpdateRequest) =>
    api.patch<VaultSummary>(`${BASE}/${id}`, payload),

  delete: (id: string) => api.delete<void>(`${BASE}/${id}`),

  replaceApiKey: (id: string, payload: VaultRotateApiKeyRequest) =>
    api.post<VaultSummary>(`${BASE}/${id}/rotate-api-key`, payload),

  setDefault: (id: string) =>
    api.post<VaultSummary>(`${BASE}/${id}/set-default`, {}),

  testConnection: (id: string) =>
    api.post<VaultTestConnectionResult>(`${BASE}/${id}/test-connection`, {}),

  revealApiKey: (id: string) =>
    api.get<VaultRevealApiKeyResponse>(`${BASE}/${id}/api-key`),

  getWalletInfo: (id: string) =>
    api.get<WalletInfoResponse>(`${BASE}/${id}/info`),

  listTypes: (
    id: string,
    params: { q?: string; include_deprecated?: boolean } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.q) qs.set("q", params.q);
    if (params.include_deprecated) qs.set("include_deprecated", "true");
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<SecretTypeSummary[]>(`${BASE}/${id}/types${suffix}`);
  },

  listSecrets: (
    id: string,
    params: {
      path?: string;
      name_contains?: string;
      tag?: string;
      limit?: number;
    } = {},
  ) => {
    const qs = new URLSearchParams();
    if (params.path) qs.set("path", params.path);
    if (params.name_contains) qs.set("name_contains", params.name_contains);
    if (params.tag) qs.set("tag", params.tag);
    if (params.limit) qs.set("limit", String(params.limit));
    const suffix = qs.toString() ? `?${qs.toString()}` : "";
    return api.get<SecretListResponse>(`${BASE}/${id}/secrets${suffix}`);
  },
};
