import { act } from "react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceChunkingTab } from "@/pages/workspace/WorkspaceChunkingTab";
import type { Workspace } from "@/lib/workspaces.types";
import type { ChunkingConfig } from "@/lib/chunking.types";
import { ApiError } from "@/lib/api";

const upsertMutate = vi.fn();
const engineMutate = vi.fn();

vi.mock("@/hooks/useChunking", () => ({
  useChunkingConfig: vi.fn(),
  useUpsertChunkingConfig: () => ({ mutate: upsertMutate, isPending: false }),
  useSetDefaultStrategy: () => ({ mutate: vi.fn(), isPending: false }),
  useSetChunkingEngine: () => ({ mutate: engineMutate, isPending: false }),
}));

vi.mock("@/hooks/useChunkingStrategies", () => ({
  useChunkingStrategies: () => ({ data: [], isLoading: false }),
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

const legacyConfig: ChunkingConfig = {
  workspace_id: "ws-1",
  strategy: "paragraph",
  max_chars: 2000,
  min_chars: 200,
  overlap_chars: 200,
  extras: {},
  default_strategy_id: null,
  engine: "legacy",
  created_at: "2026-05-19T10:00:00Z",
  updated_at: "2026-05-19T10:00:00Z",
};

const structuredConfig: ChunkingConfig = { ...legacyConfig, engine: "structured" };

function mockState(data: ChunkingConfig) {
  vi.mocked(useChunkingConfig).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useChunkingConfig>);
}

const engine409 = new ApiError(409, {
  error: "chunking_change_requires_reindex",
  workspace: "my-workspace",
  current: "engine=legacy",
  new: "engine=structured",
  action: "PUT /workspaces/my-workspace/chunking-config/engine?confirm=true",
});

describe("WorkspaceChunkingTab — moteurs", () => {
  beforeEach(() => {
    upsertMutate.mockReset();
    engineMutate.mockReset();
    toastMock.mockReset();
  });

  describe("engine=structured", () => {
    it("masque le formulaire legacy et affiche la carte info", () => {
      mockState(structuredConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      expect(screen.queryByRole("combobox", { name: "Stratégie" })).not.toBeInTheDocument();
      expect(screen.queryByDisplayValue("2000")).not.toBeInTheDocument();
      expect(screen.getByText(/Moteur : structured/i)).toBeInTheDocument();
      expect(
        screen.getByText(/définis dans les stratégies du catalogue/i),
      ).toBeInTheDocument();
      expect(screen.getByText(/Stratégie par défaut/i)).toBeInTheDocument();
    });

    it("clic « Repasser au moteur legacy » déclenche la mutation confirm=false", () => {
      mockState(structuredConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      fireEvent.click(screen.getByRole("button", { name: /Repasser au moteur legacy/i }));
      expect(engineMutate).toHaveBeenCalledTimes(1);
      expect(engineMutate.mock.calls[0]?.[0]).toEqual({ engine: "legacy", confirm: false });
    });
  });

  describe("engine=legacy", () => {
    it("affiche le bandeau, la bascule et le formulaire historique", () => {
      mockState(legacyConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      expect(screen.getByText(/moteur historique \(caractères\)/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Passer au moteur structured/i }),
      ).toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Stratégie" })).toBeInTheDocument();
      expect(screen.getByDisplayValue("2000")).toBeInTheDocument();
    });

    it("clic « Passer au moteur structured » déclenche la mutation confirm=false", () => {
      mockState(legacyConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      fireEvent.click(screen.getByRole("button", { name: /Passer au moteur structured/i }));
      expect(engineMutate).toHaveBeenCalledTimes(1);
      expect(engineMutate.mock.calls[0]?.[0]).toEqual({ engine: "structured", confirm: false });
    });

    it("409 sur la bascule ouvre le dialog puis confirme avec confirm=true", async () => {
      mockState(legacyConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      fireEvent.click(screen.getByRole("button", { name: /Passer au moteur structured/i }));

      const callbacks = engineMutate.mock.calls[0]?.[1];
      await act(async () => {
        callbacks.onError(engine409);
      });

      await waitFor(() => expect(screen.getByText(/Réindexation requise/i)).toBeInTheDocument());
      expect(screen.getByText("engine=legacy")).toBeInTheDocument();
      expect(screen.getByText("engine=structured")).toBeInTheDocument();

      fireEvent.click(screen.getByRole("button", { name: /Réindexer maintenant/i }));
      await waitFor(() => expect(engineMutate).toHaveBeenCalledTimes(2));
      expect(engineMutate.mock.calls[1]?.[0]).toEqual({ engine: "structured", confirm: true });
    });

    it("202 (reindex_triggered) affiche le toast de réindexation lancée", async () => {
      mockState(legacyConfig);
      renderWithProviders(<WorkspaceChunkingTab workspace={mockWorkspace} enabled={true} />);
      fireEvent.click(screen.getByRole("button", { name: /Passer au moteur structured/i }));

      const callbacks = engineMutate.mock.calls[0]?.[1];
      await act(async () => {
        callbacks.onSuccess({ status: "reindex_triggered", job: { id: "job-1" } });
      });

      await waitFor(() =>
        expect(toastMock).toHaveBeenCalledWith(
          expect.objectContaining({ title: expect.stringMatching(/Réindexation lancée/i) }),
        ),
      );
    });
  });
});
