import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { adminAuthConfigApi } from "@/lib/admin-auth-config";
import type { ClientSecretStatus, LocalLoginState } from "@/lib/admin-auth-config";

const CLIENT_SECRET_KEY = ["admin-auth", "oidc-client-secret"];
const LOCAL_LOGIN_KEY = ["admin-auth", "local-login"];

export function useClientSecretStatus() {
  return useQuery<ClientSecretStatus>({
    queryKey: CLIENT_SECRET_KEY,
    queryFn: () => adminAuthConfigApi.getClientSecretStatus(),
  });
}

export function useSetClientSecret() {
  const qc = useQueryClient();
  return useMutation<ClientSecretStatus, Error, string>({
    mutationFn: (value) => adminAuthConfigApi.setClientSecret(value),
    onSuccess: () => void qc.invalidateQueries({ queryKey: CLIENT_SECRET_KEY }),
  });
}

export function useLocalLogin() {
  return useQuery<LocalLoginState>({
    queryKey: LOCAL_LOGIN_KEY,
    queryFn: () => adminAuthConfigApi.getLocalLogin(),
  });
}

export function useSetLocalLogin() {
  const qc = useQueryClient();
  return useMutation<LocalLoginState, Error, boolean>({
    mutationFn: (enabled) => adminAuthConfigApi.setLocalLogin(enabled),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: LOCAL_LOGIN_KEY });
      // Le login local dépend de ce flag : rafraîchir aussi /api/auth/methods.
      void qc.invalidateQueries({ queryKey: ["auth", "methods"] });
    },
  });
}
