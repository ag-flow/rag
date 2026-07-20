import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../workspace/__tests__/testUtils";
import { McpSearchPage } from "@/pages/McpSearchPage";
import type { PlaygroundSearchResponse } from "@/lib/search-config.types";
import type { Workspace } from "@/lib/workspaces.types";

vi.mock("@/lib/search-config", () => ({
  searchConfigApi: { search: vi.fn() },
}));
vi.mock("@/lib/workspaces", () => ({
  workspacesApi: { list: vi.fn() },
}));

import { searchConfigApi } from "@/lib/search-config";
import { workspacesApi } from "@/lib/workspaces";

const searchMock = vi.mocked(searchConfigApi.search);
const listWorkspaces = vi.mocked(workspacesApi.list);

const workspace: Workspace = {
  id: "id-ws-1",
  name: "ws-1",
  label: "WS 1",
  description: "",
  indexer: { provider: "openai", model: "text-embedding-3-small", api_key_ref: null, base_url: null },
  sources_count: 1,
  documents_count: 10,
  last_indexed_at: null,
  created_at: "2026-07-01T00:00:00Z",
};

const response: PlaygroundSearchResponse = {
  query: "auth oidc",
  hybrid_enabled: false,
  rrf_k: 60,
  weight_vector: 1,
  weight_lexical: 0,
  lexical_engine: "fts",
  hits: [{ path: "a.md", chunk_index: 0, content: "Contenu du chunk A", score: 0.9123 }],
  vector_channel: [{ path: "a.md", chunk_index: 0, rank: 1, score: 0.9123 }],
  lexical_channel: [],
};

async function selectWorkspaceAndSearch(query: string) {
  await waitFor(() => {
    expect(screen.getByRole("option", { name: "ws-1" })).toBeInTheDocument();
  });
  fireEvent.change(screen.getByLabelText("Workspace"), { target: { value: "ws-1" } });
  fireEvent.change(screen.getByLabelText("Requête de recherche…"), {
    target: { value: query },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));
}

describe("McpSearchPage", () => {
  beforeEach(() => {
    searchMock.mockReset();
    listWorkspaces.mockReset();
    listWorkspaces.mockResolvedValue([workspace]);
  });

  it("lance une recherche et affiche les résultats par canaux", async () => {
    searchMock.mockResolvedValue(response);
    renderWithProviders(<McpSearchPage />);

    await selectWorkspaceAndSearch("auth oidc");

    await waitFor(() => {
      expect(screen.getByText("Contenu du chunk A")).toBeInTheDocument();
    });
    expect(searchMock).toHaveBeenCalledWith("ws-1", { query: "auth oidc", top_k: 10 });
    expect(screen.getByText("Fusion (RRF)")).toBeInTheDocument();
    expect(screen.getByText("Canal vectoriel")).toBeInTheDocument();
    expect(screen.getByText("Canal lexical")).toBeInTheDocument();
  });

  it("affiche le bandeau hybride non activé quand hybrid_enabled est false", async () => {
    searchMock.mockResolvedValue(response);
    renderWithProviders(<McpSearchPage />);

    await selectWorkspaceAndSearch("auth oidc");

    await waitFor(() => {
      expect(
        screen.getByText(
          "Recherche hybride non activée sur ce workspace — le canal lexical est vide.",
        ),
      ).toBeInTheDocument();
    });
  });

  it("désactive le bouton tant qu'aucun workspace n'est sélectionné", async () => {
    renderWithProviders(<McpSearchPage />);

    fireEvent.change(screen.getByLabelText("Requête de recherche…"), {
      target: { value: "auth" },
    });
    expect(screen.getByRole("button", { name: "Rechercher" })).toBeDisabled();
    expect(searchMock).not.toHaveBeenCalled();
  });

  it("mentionne le contrat MCP avec un lien", () => {
    renderWithProviders(<McpSearchPage />);

    expect(
      screen.getByText("Cette page utilise la même recherche que les agents MCP."),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Contrat des outils MCP" })).toHaveAttribute(
      "href",
      "/api/contracts/mcp-tools",
    );
  });
});
