import { describe, it, expect, beforeAll, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { I18nextProvider, initReactI18next } from "react-i18next";
import i18next from "i18next";

import frIntegration from "@/i18n/fr/integration.json";
import { IntegrationContractsPage } from "@/pages/IntegrationContractsPage";

vi.mock("@/lib/contracts", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/contracts")>();
  return {
    ...actual,
    contractsApi: {
      getApikeyOpenapi: vi.fn().mockResolvedValue({
        servers: [{ url: "https://rag.yoops.org" }],
        paths: {
          "/api/v1/search": { post: {} },
          "/api/workspaces/{name}/index": { post: {}, delete: {} },
        },
      }),
      getMcpTools: vi.fn().mockResolvedValue({
        count: 2,
        tools: [
          {
            name: "rag_search",
            description: "Recherche sémantique\nseconde ligne",
            inputSchema: {
              properties: { workspace: { type: "string" }, query: { type: "string" } },
              required: ["workspace", "query"],
            },
          },
          { name: "list_workspaces", description: "Liste", inputSchema: { properties: {} } },
        ],
      }),
    },
  };
});

const testI18n = i18next.createInstance();

beforeAll(async () => {
  await testI18n.use(initReactI18next).init({
    lng: "fr",
    fallbackLng: "fr",
    ns: ["integration"],
    defaultNS: "integration",
    resources: { fr: { integration: frIntegration } },
    interpolation: { escapeValue: false },
  });
});

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <I18nextProvider i18n={testI18n}>
        <IntegrationContractsPage />
      </I18nextProvider>
    </QueryClientProvider>,
  );
}

describe("IntegrationContractsPage", () => {
  it("expose les URLs des contrats à importer", () => {
    renderPage();
    expect(
      screen.getByText(`${window.location.origin}/api/contracts/workflow-events`),
    ).toBeInTheDocument();
    expect(
      screen.getByText(`${window.location.origin}/api/contracts/openapi-apikey`),
    ).toBeInTheDocument();
    expect(screen.getByText(`${window.location.origin}/openapi.json`)).toBeInTheDocument();
  });

  it("liste les endpoints (méthode + URL) du contrat par clé API", async () => {
    renderPage();
    // Les endpoints résolus depuis le `servers` du contrat.
    expect(await screen.findByText("https://rag.yoops.org/api/v1/search")).toBeInTheDocument();
    // /index apparaît deux fois (POST + DELETE).
    expect(
      screen.getAllByText("https://rag.yoops.org/api/workspaces/{name}/index"),
    ).toHaveLength(2);
    // méthodes présentes (POST pour search + index, DELETE pour index)
    expect(screen.getAllByText("POST").length).toBeGreaterThanOrEqual(2);
    expect(screen.getByText("DELETE")).toBeInTheDocument();
  });

  it("explore les outils MCP à l'ouverture (nom + paramètres)", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /Explorer les outils/i }));
    expect(await screen.findByText("rag_search")).toBeInTheDocument();
    expect(screen.getByText("list_workspaces")).toBeInTheDocument();
    // paramètres affichés (le nom apparaît dans une pastille).
    expect(screen.getByText("workspace")).toBeInTheDocument();
    expect(screen.getByText("query")).toBeInTheDocument();
  });
});
