import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { workspaceApiKeysApi } from "@/lib/workspace-apikeys";
import type { ApiKeyCreate } from "@/lib/workspace-apikeys.types";

const KEY = (ws: string) => ["workspace-api-keys", ws] as const;

export function useWorkspaceApiKeys(workspaceName: string) {
  return useQuery({
    queryKey: KEY(workspaceName),
    queryFn: () => workspaceApiKeysApi.list(workspaceName),
    staleTime: 30_000,
  });
}

export function useCreateApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: ApiKeyCreate) =>
      workspaceApiKeysApi.create(workspaceName, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}

export function useRotateApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      workspaceApiKeysApi.rotate(workspaceName, keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}

export function useRevokeApiKey(workspaceName: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) =>
      workspaceApiKeysApi.revoke(workspaceName, keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY(workspaceName) }),
  });
}
