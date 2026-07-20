import { api } from "@/lib/api";
import type {
  KeyScope,
  UserApiKey,
  UserApiKeyCreate,
  UserApiKeyCreated,
  UserApiKeyRotated,
} from "@/lib/user-api-keys.types";

const BASE = "/api/me/api-keys";

export const userApiKeysApi = {
  list: () => api.get<UserApiKey[]>(BASE),
  create: (payload: UserApiKeyCreate) => api.post<UserApiKeyCreated>(BASE, payload),
  rotate: (keyId: string) => api.post<UserApiKeyRotated>(`${BASE}/${keyId}/rotate`, {}),
  revoke: (keyId: string) => api.delete<void>(`${BASE}/${keyId}`),
  setScope: (keyId: string, scope: KeyScope) =>
    api.put<void>(`${BASE}/${keyId}/scope`, { scope }),
};
