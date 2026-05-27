import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { oidcConfigApi } from "@/lib/oidc-config";
import type { OidcConfig, OidcConfigCreate } from "@/lib/oidc-config.types";

/**
 * Récupère la config OIDC.
 * Backend renvoie 503 quand non configurée (cf. test_admin_oidc.py:21) — on
 * intercepte ce cas et retourne `null` pour permettre au composant d'afficher
 * un form vide.
 */
export function useOidcConfig() {
  return useQuery<OidcConfig | null>({
    queryKey: ["oidc-config"],
    queryFn: async () => {
      try {
        return await oidcConfigApi.get();
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          return null;
        }
        throw err;
      }
    },
  });
}

export function useUpsertOidcConfig() {
  const qc = useQueryClient();
  return useMutation<OidcConfig, Error, OidcConfigCreate>({
    mutationFn: (payload) => oidcConfigApi.upsert(payload),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: ["oidc-config"] });
    },
  });
}
