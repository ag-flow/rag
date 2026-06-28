import { useQuery } from "@tanstack/react-query";

export type AuthMethods = {
  oidc_configured: boolean;
  local_auth_enabled: boolean;
  needs_setup: boolean;
};

export function useAuthMethods() {
  return useQuery<AuthMethods>({
    queryKey: ["auth", "methods"],
    queryFn: async () => {
      const r = await fetch("/api/auth/methods");
      if (!r.ok) throw new Error(`auth_methods_${r.status}`);
      return (await r.json()) as AuthMethods;
    },
    staleTime: Infinity,
    retry: false,
  });
}
