import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { userApiKeysApi } from "@/lib/user-api-keys";
import type { UserApiKeyCreate, UserApiKeyUpdate } from "@/lib/user-api-keys.types";

const KEY = ["user-api-keys"] as const;

export function useUserApiKeys() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => userApiKeysApi.list(),
    staleTime: 30_000,
  });
}

export function useCreateUserApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: UserApiKeyCreate) => userApiKeysApi.create(payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRotateUserApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => userApiKeysApi.rotate(keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useRevokeUserApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (keyId: string) => userApiKeysApi.revoke(keyId),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}

export function useUpdateUserApiKey() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ keyId, payload }: { keyId: string; payload: UserApiKeyUpdate }) =>
      userApiKeysApi.update(keyId, payload),
    onSuccess: () => void qc.invalidateQueries({ queryKey: KEY }),
  });
}
