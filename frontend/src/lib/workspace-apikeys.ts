import { api } from "@/lib/api";
import type {
  ApiKey,
  ApiKeyCreate,
  ApiKeyCreated,
  ApiKeyRotated,
} from "@/lib/workspace-apikeys.types";

const BASE = (name: string) => `/api/admin/workspaces/${name}/api-keys`;

export const workspaceApiKeysApi = {
  list: (workspaceName: string) =>
    api.get<ApiKey[]>(BASE(workspaceName)),

  create: (workspaceName: string, payload: ApiKeyCreate) =>
    api.post<ApiKeyCreated>(BASE(workspaceName), payload),

  rotate: (workspaceName: string, keyId: string) =>
    api.post<ApiKeyRotated>(`${BASE(workspaceName)}/${keyId}/rotate`, {}),

  revoke: (workspaceName: string, keyId: string) =>
    api.delete<void>(`${BASE(workspaceName)}/${keyId}`),
};
