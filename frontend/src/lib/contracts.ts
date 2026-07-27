import { api } from "@/lib/api";

/** OpenAPI minimal : ce dont on a besoin pour lister les endpoints (méthode + URL). */
export interface OpenApiContract {
  servers?: { url: string }[];
  paths?: Record<string, Record<string, unknown>>;
}

export interface EndpointRef {
  method: string; // GET, POST…
  url: string; // URL absolue (server + path)
  summary: string; // résumé lisible de l'opération (vide si absent du contrat)
}

const HTTP_METHODS = ["get", "post", "put", "patch", "delete"];

/** Schéma d'entrée JSON d'un outil MCP (sous-ensemble utile à l'affichage). */
export interface McpInputSchema {
  properties?: Record<string, { type?: string | string[]; description?: string }>;
  required?: string[];
}

export interface McpTool {
  name: string;
  description?: string;
  inputSchema?: McpInputSchema;
}

export interface McpToolsContract {
  count: number;
  tools: McpTool[];
}

export interface McpParam {
  name: string;
  type: string;
  required: boolean;
  description: string;
}

export const contractsApi = {
  getApikeyOpenapi: () => api.get<OpenApiContract>("/api/contracts/openapi-apikey"),
  getMcpTools: () => api.get<McpToolsContract>("/api/contracts/mcp-tools"),
};

/** Aplati l'inputSchema d'un outil MCP en liste de paramètres lisibles. */
export function listToolParams(tool: McpTool): McpParam[] {
  const props = tool.inputSchema?.properties ?? {};
  const required = new Set(tool.inputSchema?.required ?? []);
  return Object.entries(props).map(([name, schema]) => ({
    name,
    type: Array.isArray(schema.type) ? schema.type.join(" | ") : (schema.type ?? "any"),
    required: required.has(name),
    description: schema.description ?? "",
  }));
}

/** Aplati un contrat OpenAPI en liste d'endpoints absolus (méthode + URL). */
export function listEndpoints(contract: OpenApiContract, fallbackBase: string): EndpointRef[] {
  const base = (contract.servers?.[0]?.url ?? fallbackBase).replace(/\/$/, "");
  const out: EndpointRef[] = [];
  for (const [path, operations] of Object.entries(contract.paths ?? {})) {
    for (const [method, op] of Object.entries(operations)) {
      if (HTTP_METHODS.includes(method.toLowerCase())) {
        const summary =
          op && typeof op === "object" && typeof (op as { summary?: unknown }).summary === "string"
            ? (op as { summary: string }).summary
            : "";
        out.push({ method: method.toUpperCase(), url: `${base}${path}`, summary });
      }
    }
  }
  return out;
}
