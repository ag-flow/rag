import { act } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "./testUtils";
import { WorkspaceChunkingTab } from "@/pages/workspace/WorkspaceChunkingTab";
import type { Workspace } from "@/lib/workspaces.types";
import type { ChunkingConfig } from "@/lib/chunking.types";
import { ApiError } from "@/lib/api";

const upsertMutate = vi.fn();

vi.mock("@/hooks/useChunking", () => ({
  useChunkingConfig: vi.fn(),
  useUpsertChunkingConfig: () => ({ mutate: upsertMutate, isPending: false }),
}));

const toastMock = vi.fn();
vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: toastMock }),
}));

import { useChunkingConfig } from "@/hooks/useChunking";

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

const mockConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

function mockState(data: ChunkingConfig | undefined, isLoading = false) {
  vi.mocked(useChunkingConfig).mockReturnValue({
    data,
    isLoading,
  } as unknown as ReturnType<typeof useChunkingConfig>);
}

describe("WorkspaceChunkingTab", () => {
  beforeEach(() => {
    upsertMutate.mockReset();
    toastMock.mockReset();
  });

  it("affiche LoadingSpinner pendant le fetch", () => {
    mockState(undefined, true);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.queryByText(/Configuration du chunking/i)).not.toBeInTheDocument();
  });

  it("rend le form pré-rempli avec la config actuelle", () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByText(/Configuration du chunking/i)).toBeInTheDocument();
    expect(screen.getByDisplayValue("2000")).toBeInTheDocument();
    expect(screen.getAllByDisplayValue("200")).toHaveLength(2); // min + overlap
  });

  it("bouton Enregistrer disabled tant que form clean", () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    expect(screen.getByRole("button", { name: /^Enregistrer$/i })).toBeDisabled();
  });

  it("submit déclenche upsert avec confirm=false", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });

    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs).toMatchObject({
      payload: expect.objectContaining({ max_chars: 1500 }),
      confirm: false,
    });
  });

  it("toast noChange sur status no_change", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    await act(async () => {
      callbacks.onSuccess({ status: "no_change" });
    });

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/Aucune modification/i) }),
      ),
    );
  });

  it("toast success sur status updated", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    await act(async () => {
      callbacks.onSuccess({
        status: "updated",
        config: { ...mockConfig, max_chars: 1500 },
      });
    });

    await waitFor(() =>
      expect(toastMock).toHaveBeenCalledWith(
        expect.objectContaining({ title: expect.stringMatching(/Configuration enregistrée/i) }),
      ),
    );
  });

  it("ouvre le dialog 409 avec current/new sur ApiError(409)", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callbacks = upsertMutate.mock.calls[0]?.[1];
    await act(async () => {
      callbacks.onError(
        new ApiError(409, {
          error: "chunking_change_requires_reindex",
          workspace: "my-workspace",
          current: "paragraph (max=2000, min=200, overlap=200)",
          new: "paragraph (max=1500, min=200, overlap=200)",
          action: "PUT /workspaces/my-workspace/chunking-config?confirm=true",
        }),
      );
    });

    await waitFor(() =>
      expect(screen.getByText(/Réindexation requise/i)).toBeInTheDocument(),
    );
    expect(
      screen.getByText("paragraph (max=2000, min=200, overlap=200)"),
    ).toBeInTheDocument();
    expect(
      screen.getByText("paragraph (max=1500, min=200, overlap=200)"),
    ).toBeInTheDocument();
  });

  it("clic Réindexer maintenant déclenche 2ᵉ upsert avec confirm=true", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    await act(async () => {
      upsertMutate.mock.calls[0]?.[1].onError(
        new ApiError(409, {
          error: "chunking_change_requires_reindex",
          workspace: "my-workspace",
          current: "paragraph (max=2000, min=200, overlap=200)",
          new: "paragraph (max=1500, min=200, overlap=200)",
          action: "PUT /workspaces/my-workspace/chunking-config?confirm=true",
        }),
      );
    });

    await waitFor(() => screen.getByText(/Réindexation requise/i));
    fireEvent.click(screen.getByRole("button", { name: /Réindexer maintenant/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalledTimes(2));
    const secondCall = upsertMutate.mock.calls[1]?.[0];
    expect(secondCall).toMatchObject({ confirm: true });
  });

  it("le Select stratégie propose paragraph ET markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    expect(
      screen.getByRole("option", { name: /Paragraphes \(par défaut\)/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("option", { name: /^Markdown$/i }),
    ).toBeInTheDocument();
  });

  it("le helper text change quand on sélectionne markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /^Markdown$/i }));
    expect(
      screen.getByText(/Respecte la structure d'un document Markdown/i),
    ).toBeInTheDocument();
  });

  it("submit envoie extras:{} après changement de strategy paragraph → markdown", async () => {
    const user = userEvent.setup();
    mockState(mockConfig); // strategy: 'paragraph', extras: {}
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    await user.click(screen.getByRole("combobox"));
    await user.click(screen.getByRole("option", { name: /^Markdown$/i }));
    await user.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs?.payload?.strategy).toBe("markdown");
    expect(callArgs?.payload?.extras).toEqual({});
  });

  it("submit préserve data.extras quand strategy markdown reste markdown", async () => {
    const user = userEvent.setup();
    const adminConfig: ChunkingConfig = {
      ...mockConfig,
      strategy: "markdown",
      extras: { heading_levels: [1, 3] },
    };
    mockState(adminConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const maxInput = screen.getByDisplayValue("2000") as HTMLInputElement;
    fireEvent.change(maxInput, { target: { value: "1500" } });
    await user.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => expect(upsertMutate).toHaveBeenCalled());
    const callArgs = upsertMutate.mock.calls[0]?.[0];
    expect(callArgs?.payload?.strategy).toBe("markdown");
    expect(callArgs?.payload?.extras).toEqual({ heading_levels: [1, 3] });
  });

  it("erreur Zod min ≥ max → message d'erreur, pas de submit", async () => {
    mockState(mockConfig);
    renderWithProviders(
      <WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />,
    );
    const inputs = screen.getAllByDisplayValue("200");
    const minInput = inputs[0];
    if (!minInput) throw new Error("min_chars input introuvable");
    // min_chars = 3000 (premier input ayant displayValue=200)
    fireEvent.change(minInput, { target: { value: "3000" } });
    fireEvent.click(screen.getByRole("button", { name: /^Enregistrer$/i }));

    await waitFor(() => {
      expect(
        screen.getByText(/Doit être inférieur à la taille max/i),
      ).toBeInTheDocument();
    });
    expect(upsertMutate).not.toHaveBeenCalled();
  });
});
