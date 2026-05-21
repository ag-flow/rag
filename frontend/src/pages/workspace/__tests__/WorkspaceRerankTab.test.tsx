import { describe, it, expect, vi } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceRerankTab } from "@/pages/workspace/WorkspaceRerankTab";
import type { Workspace } from "@/lib/workspaces.types";
import type { RerankConfig } from "@/lib/rerank.types";

const upsertMutate = vi.fn();

vi.mock("@/hooks/useRerank", () => ({
  useRerankConfig: vi.fn(),
  useUpsertRerankConfig: () => ({ mutate: upsertMutate, isPending: false }),
  useDeleteRerankConfig: () => ({ mutate: vi.fn(), isPending: false }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useRerankConfig } from "@/hooks/useRerank";

const mockWorkspace: Workspace = {
  id: "ws-1",
  name: "my-workspace",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: "openai_key",
    base_url: null,
  },
  sources_count: 0,
  documents_count: 0,
  last_indexed_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

const mockConfig: RerankConfig = {
  workspace_id: "ws-1",
  provider: "cohere",
  model: "rerank-english-v3.0",
  api_key_ref: "cohere_rerank_key",
  base_url: null,
  top_k_pre_rerank: 50,
  created_at: "2026-05-18T10:00:00Z",
  updated_at: "2026-05-18T10:00:00Z",
};

function mockState(data: RerankConfig | null, isLoading = false) {
  vi.mocked(useRerankConfig).mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useRerankConfig>);
}

describe("WorkspaceRerankTab", () => {
  it("état vide : form vide + bouton Activer + pas de bouton Supprimer", () => {
    mockState(null);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/Reranking \(optionnel\)/i)).toBeInTheDocument();
    expect(screen.queryByText(/^actif$/i)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Activer/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Supprimer la config/i })).not.toBeInTheDocument();
  });

  it("état configuré : form pré-rempli + badge actif + bouton Supprimer", () => {
    mockState(mockConfig);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/^actif$/i)).toBeInTheDocument();
    // Le Select modèle affiche la valeur sélectionnée (peut apparaître dans trigger + options)
    expect(screen.getAllByText("rerank-english-v3.0").length).toBeGreaterThan(0);
    expect(screen.getByDisplayValue("cohere_rerank_key")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Enregistrer/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Supprimer la config/i })).toBeInTheDocument();
  });

  it("submit avec valeurs valides appelle upsert.mutate avec le payload", async () => {
    upsertMutate.mockClear();
    mockState(mockConfig);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    // Modifier api_key_ref pour rendre le form dirty
    const apiKeyInput = screen.getByDisplayValue("cohere_rerank_key");
    fireEvent.change(apiKeyInput, { target: { value: "new_cohere_key" } });
    fireEvent.click(screen.getByRole("button", { name: /Enregistrer/i }));
    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    expect(upsertMutate.mock.calls[0]?.[0]).toMatchObject({
      provider: "cohere",
      model: "rerank-english-v3.0",
      api_key_ref: "new_cohere_key",
      top_k_pre_rerank: 50,
    });
  });

  it("affiche la dernière modification quand configuré", () => {
    mockState({ ...mockConfig, updated_at: new Date(Date.now() - 2 * 3600_000).toISOString() });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/Dernière modification/i)).toBeInTheDocument();
  });

  it("ne rend pas le footer lastModified quand non configuré", () => {
    mockState(null);
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.queryByText(/Dernière modification/i)).not.toBeInTheDocument();
  });

  it("désactive base_url quand provider est cohere", () => {
    mockState({ ...mockConfig, provider: "cohere" });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    const baseUrlInput = screen
      .getAllByPlaceholderText(/non applicable/i)
      .find((el) => el.getAttribute("name") === "base_url") as HTMLInputElement | undefined;
    expect(baseUrlInput).toBeDefined();
    expect(baseUrlInput).toBeDisabled();
  });

  it("désactive api_key_ref quand provider est ollama", () => {
    mockState({
      ...mockConfig,
      provider: "ollama",
      api_key_ref: null,
      base_url: "https://ollama.example.com",
      model: "bge-reranker-v2-m3",
    });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    const apiKeyInput = screen
      .getAllByPlaceholderText(/non applicable/i)
      .find((el) => el.getAttribute("name") === "api_key_ref") as HTMLInputElement | undefined;
    expect(apiKeyInput).toBeDefined();
    expect(apiKeyInput).toBeDisabled();
  });

  it("affiche erreur Zod required_for_provider si cohere sans api_key_ref", async () => {
    mockState({ ...mockConfig, api_key_ref: null });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    // Modifier top_k pour rendre le form dirty, puis soumettre
    const topKInput = screen.getByRole("spinbutton");
    fireEvent.change(topKInput, { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: /Enregistrer/i }));
    expect(await screen.findByText(/Requis pour ce provider/i)).toBeInTheDocument();
  });

  it("affiche erreur Zod required_for_provider si ollama sans base_url", async () => {
    mockState({
      ...mockConfig,
      provider: "ollama",
      api_key_ref: null,
      base_url: null,
      model: "bge-reranker-v2-m3",
    });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled={true} />);
    // Modifier top_k pour rendre le form dirty, puis soumettre
    const topKInput = screen.getByRole("spinbutton");
    fireEvent.change(topKInput, { target: { value: "60" } });
    fireEvent.click(screen.getByRole("button", { name: /Enregistrer/i }));
    expect(await screen.findByText(/Requis pour ce provider/i)).toBeInTheDocument();
  });
});
