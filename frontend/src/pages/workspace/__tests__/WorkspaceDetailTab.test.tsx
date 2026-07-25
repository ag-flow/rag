import { describe, it, expect, vi } from "vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceDetailTab } from "@/pages/workspace/WorkspaceDetailTab";
import { workspacesApi } from "@/lib/workspaces";
import type { Workspace } from "@/lib/workspaces.types";

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@/lib/workspaces", () => ({
  workspacesApi: {
    refreshEndpoint: vi.fn(),
  },
}));

const refreshEndpoint = vi.mocked(workspacesApi.refreshEndpoint);

const mockWorkspace: Workspace = {
  id: "abc-123",
  name: "my-workspace",
  endpoint_id: null,
  label: "My workspace",
  description: "",
  indexer: {
    provider: "openai",
    model: "text-embedding-3-small",
    api_key_ref: "openai_key",
    base_url: null,
  },
  sources_count: 3,
  documents_count: 150,
  last_indexed_at: null,
  created_at: "2026-01-01T00:00:00Z",
};

describe("WorkspaceDetailTab", () => {
  it("affiche les statistiques du workspace", () => {
    renderWithProviders(<WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText(/3 sources/)).toBeInTheDocument();
    expect(screen.getByText(/150 documents/)).toBeInTheDocument();
  });

  it("affiche le nom et l'id du workspace", () => {
    renderWithProviders(<WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText("my-workspace")).toBeInTheDocument();
    expect(screen.getByText("abc-123")).toBeInTheDocument();
  });

  it("la référence de clé est affichée en lecture seule (pas de bouton changer la clé)", () => {
    renderWithProviders(<WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByText("openai_key")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /changer la clé/i })).not.toBeInTheDocument();
  });

  it("refresh désactivé quand le workspace n'a pas d'endpoint d'origine", () => {
    renderWithProviders(<WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />);
    expect(screen.getByRole("button", { name: /rafraîchir depuis l'endpoint/i })).toBeDisabled();
  });

  it("refresh actif : clic → POST refresh-endpoint sans confirm", async () => {
    refreshEndpoint.mockResolvedValue({ indexer: "updated", rerank: "none", llm: "none" });
    renderWithProviders(
      <WorkspaceDetailTab workspace={{ ...mockWorkspace, endpoint_id: "ep-1" }} enabled={true} />,
    );
    const btn = screen.getByRole("button", { name: /rafraîchir depuis l'endpoint/i });
    expect(btn).toBeEnabled();
    fireEvent.click(btn);
    await waitFor(() => {
      expect(refreshEndpoint).toHaveBeenCalledWith("my-workspace", false);
    });
  });
});
