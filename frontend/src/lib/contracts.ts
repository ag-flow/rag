import { api } from "@/lib/api";

/** OpenAPI minimal : ce dont on a besoin pour lister les endpoints (méthode + URL). */
export interface OpenApiContract {
  servers?: { url: string }[];
  paths?: Record<string, Record<string, unknown>>;
}

export interface EndpointRef {
  method: string; // GET, POST…
  url: string; // URL absolue (server + path)
}

const HTTP_METHODS = ["get", "post", "put", "patch", "delete"];

export const contractsApi = {
  getApikeyOpenapi: () => api.get<OpenApiContract>("/api/contracts/openapi-apikey"),
};

/** Aplati un contrat OpenAPI en liste d'endpoints absolus (méthode + URL). */
export function listEndpoints(contract: OpenApiContract, fallbackBase: string): EndpointRef[] {
  const base = (contract.servers?.[0]?.url ?? fallbackBase).replace(/\/$/, "");
  const out: EndpointRef[] = [];
  for (const [path, operations] of Object.entries(contract.paths ?? {})) {
    for (const method of Object.keys(operations)) {
      if (HTTP_METHODS.includes(method.toLowerCase())) {
        out.push({ method: method.toUpperCase(), url: `${base}${path}` });
      }
    }
  }
  return out;
}
