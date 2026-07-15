import { api } from "@/lib/api";

// Réglages d'auth pilotés par l'IHM, persistés côté backend dans admin.env.
const BASE = "/api/admin";

export type ClientSecretStatus = { configured: boolean };
export type LocalLoginState = { enabled: boolean };

export const adminAuthConfigApi = {
  getClientSecretStatus: () =>
    api.get<ClientSecretStatus>(`${BASE}/oidc/client-secret`),
  setClientSecret: (value: string) =>
    api.put<ClientSecretStatus>(`${BASE}/oidc/client-secret`, { value }),
  getLocalLogin: () => api.get<LocalLoginState>(`${BASE}/auth/local-login`),
  setLocalLogin: (enabled: boolean) =>
    api.put<LocalLoginState>(`${BASE}/auth/local-login`, { enabled }),
};
