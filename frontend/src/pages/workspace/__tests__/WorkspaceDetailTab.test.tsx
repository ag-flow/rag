import { describe, it, expect, vi } from "vitest";
import { fireEvent, screen } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceDetailTab } from "@/pages/workspace/WorkspaceDetailTab";
import type { Workspace } from "@/lib/workspaces.types";

const mockMutate = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useUpdateApiKeyRef: () => ({
    mutate: mockMutate,
    isPending: false,
  }),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

vi.mock("@/hooks/useHarpocrateVaults", () => ({
  useProviderKeysByProvider: () => ({
    data: [
      {
        id: "pk-1",
        key_id: "openai-prod",
        label: "OpenAI prod",
        provider: "openai",
        harpo_path: "openai_key",
        vault_name: "rag",
        vault_label: "Coffre RAG",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: "pk-2",
        key_id: "voyage-prod",
        label: "Voyage prod",
        provider: "openai",
        harpo_path: "voyage_key",
        vault_name: "rag",
        vault_label: "Coffre RAG",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
  }),
}));

const mockWorkspace: Workspace = {
  id: "abc-123",
  name: "my-workspace",
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
    renderWithProviders(
      <WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByText(/3 sources/)).toBeInTheDocument();
    expect(screen.getByText(/150 documents/)).toBeInTheDocument();
  });

  it("affiche le nom et l'id du workspace", () => {
    renderWithProviders(
      <WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByText("my-workspace")).toBeInTheDocument();
    expect(screen.getByText("abc-123")).toBeInTheDocument();
  });

  it("le bouton Changer la clé est désactivé tant que la valeur est inchangée", () => {
    renderWithProviders(
      <WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />,
    );
    const saveBtn = screen.getByRole("button", { name: /changer la clé/i });
    expect(saveBtn).toBeDisabled();
  });

  it("affiche le label de la clé couramment référencée", () => {
    renderWithProviders(
      <WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />,
    );
    // openai_key est résolu vers son label + coffre dans le sélecteur.
    expect(screen.getByText("OpenAI prod — Coffre RAG")).toBeInTheDocument();
  });

  it("changer la clé : autre clé sélectionnée → mutation indexer.api_key_ref", async () => {
    mockMutate.mockClear();
    renderWithProviders(
      <WorkspaceDetailTab workspace={mockWorkspace} enabled={true} />,
    );
    fireEvent.click(screen.getByRole("combobox", { name: /Référence de clé API/i }));
    fireEvent.click(await screen.findByText("Voyage prod — Coffre RAG"));
    const saveBtn = screen.getByRole("button", { name: /changer la clé/i });
    expect(saveBtn).toBeEnabled();
    fireEvent.click(saveBtn);
    expect(mockMutate).toHaveBeenCalledWith(
      { indexer: { api_key_ref: "voyage_key" } },
      expect.anything(),
    );
  });
});
