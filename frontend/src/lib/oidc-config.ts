import { api } from "@/lib/api";
import type { OidcConfig, OidcConfigCreate } from "@/lib/oidc-config.types";

const BASE = "/api/admin/oidc";

export const oidcConfigApi = {
  get: () => api.get<OidcConfig>(BASE),
  upsert: (payload: OidcConfigCreate) => api.post<OidcConfig>(BASE, payload),
};
