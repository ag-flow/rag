import { describe, it, expect, vi } from "vitest";
import { screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceRerankTab } from "@/pages/workspace/WorkspaceRerankTab";
import type { Workspace } from "@/lib/workspaces.types";

// L'onglet Rerank est en lecture seule : la config vient de l'endpoint choisi
// à la création (snapshot). Seul api_key_ref se change (onglet Détail).

const mockUseRerankConfig = vi.fn();

vi.mock("@/hooks/useRerank", () => ({
  useRerankConfig: (...args: unknown[]) => mockUseRerankConfig(...args),
}));

const mockWorkspace: Workspace = {
  id: "abc-123",
  name: "my-workspace",
  label: "My workspace",
  description: "",
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

describe("WorkspaceRerankTab", () => {
  it("affiche la config rerank en lecture seule", () => {
    mockUseRerankConfig.mockReturnValue({
      data: {
        provider: "cohere",
        model: "rerank-v3.5",
        base_url: null,
        api_key_ref: "cohere_rerank_key",
        top_k_pre_rerank: 25,
      },
      isLoading: false,
    });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled />);

    expect(screen.getByText("Reranking")).toBeInTheDocument();
    expect(screen.getByText("cohere")).toBeInTheDocument();
    expect(screen.getByText("rerank-v3.5")).toBeInTheDocument();
    expect(screen.getByText("cohere_rerank_key")).toBeInTheDocument();
    expect(screen.getByText("25")).toBeInTheDocument();
  });

  it("affiche l'état vide quand aucun rerank n'est configuré", () => {
    mockUseRerankConfig.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled />);

    expect(screen.getByText(/Ajoute une seconde passe de tri/)).toBeInTheDocument();
  });

  it("affiche l'avertissement d'immutabilité", () => {
    mockUseRerankConfig.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled />);

    // Le warning est toujours visible (config figée par le snapshot endpoint).
    const warnings = screen.getAllByText(/./, { selector: ".text-amber-900" });
    expect(warnings.length).toBeGreaterThan(0);
  });

  it("affiche un spinner pendant le chargement", () => {
    mockUseRerankConfig.mockReturnValue({ data: undefined, isLoading: true });
    const { container } = renderWithProviders(
      <WorkspaceRerankTab workspace={mockWorkspace} enabled />,
    );
    expect(container.querySelector("svg")).toBeInTheDocument();
  });

  it("interroge la config avec le nom du workspace et le flag enabled", () => {
    mockUseRerankConfig.mockReturnValue({ data: undefined, isLoading: false });
    renderWithProviders(<WorkspaceRerankTab workspace={mockWorkspace} enabled />);
    expect(mockUseRerankConfig).toHaveBeenCalledWith("my-workspace", true);
  });
});
