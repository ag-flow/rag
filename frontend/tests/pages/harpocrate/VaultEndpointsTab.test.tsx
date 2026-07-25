import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor, within } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import * as apiModule from "@/lib/api";
import { VaultEndpointsTab } from "@/pages/harpocrate/VaultEndpointsTab";
import type { VaultEndpoint } from "@/lib/vault-endpoints.types";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const EP: VaultEndpoint = {
  id: "ep-1",
  vault_id: "v-1",
  label: "Docs internes (Ollama)",
  slug: "docs-internes-ollama",
  indexer: {
    provider: "ollama",
    model: "nomic-embed-text",
    api_key_ref: null,
    base_url: "http://ollama:11434",
  },
  rerank: {
    provider: "cohere",
    model: "rerank-v3.5",
    api_key_ref: "ref-cohere",
    base_url: null,
    top_k_pre_rerank: 25,
  },
  llm: null,
  created_at: "2026-07-01T00:00:00Z",
  updated_at: "2026-07-01T00:00:00Z",
};

describe("VaultEndpointsTab", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("liste les endpoints avec slug, vectorisation et rerank", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([EP]);
    render(
      <Wrapper>
        <VaultEndpointsTab vaultId="v-1" />
      </Wrapper>,
    );
    expect(await screen.findByText("Docs internes (Ollama)")).toBeInTheDocument();
    expect(screen.getByText("docs-internes-ollama")).toBeInTheDocument();
    expect(screen.getByText("ollama/nomic-embed-text")).toBeInTheDocument();
    expect(screen.getByText("cohere/rerank-v3.5")).toBeInTheDocument();
  });

  it("état vide + ouverture du formulaire de création (aperçu slug)", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([]);
    render(
      <Wrapper>
        <VaultEndpointsTab vaultId="v-1" />
      </Wrapper>,
    );
    expect(await screen.findByText(/Aucun endpoint/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Créer un endpoint/i }));
    const labelInput = await screen.findByPlaceholderText(/Docs internes/);
    fireEvent.change(labelInput, { target: { value: "Été & Café 2026" } });
    expect(screen.getByText(/slug : ete-cafe-2026/)).toBeInTheDocument();
  });

  it("supprime après confirmation", async () => {
    vi.spyOn(apiModule.api, "get").mockResolvedValue([EP]);
    const deleteSpy = vi.spyOn(apiModule.api, "delete").mockResolvedValue(undefined);
    render(
      <Wrapper>
        <VaultEndpointsTab vaultId="v-1" />
      </Wrapper>,
    );
    await screen.findByText("Docs internes (Ollama)");
    fireEvent.click(screen.getByRole("button", { name: /Supprimer/i }));
    const dialog = await screen.findByRole("alertdialog");
    fireEvent.click(within(dialog).getByRole("button", { name: /Supprimer/i }));
    await waitFor(() =>
      expect(deleteSpy).toHaveBeenCalledWith(
        "/api/admin/harpocrate-vaults/v-1/endpoints/ep-1",
      ),
    );
  });
});
