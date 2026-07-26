import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, waitFor } from "@testing-library/react";
import { renderWithProviders } from "../../workspace/__tests__/testUtils";
import { EndpointFormDialog } from "@/pages/harpocrate/EndpointFormDialog";

vi.mock("@/lib/vault-endpoints", () => ({
  vaultEndpointsApi: {
    list: vi.fn().mockResolvedValue([]),
    create: vi.fn(),
    update: vi.fn(),
    remove: vi.fn(),
    test: vi.fn(),
  },
}));
vi.mock("@/hooks/useModels", () => ({
  useModels: () => ({
    data: [
      { provider: "ollama", model: "mxbai-embed-large", kind: "embedding", dimension: 1024 },
      { provider: "ollama", model: "qwen3:14b", kind: "llm", dimension: null },
    ],
  }),
  useRerankPairings: () => ({ data: [] }),
}));
vi.mock("@/hooks/useProviderKeys", () => ({
  useProviderKeys: () => ({ data: [] }),
}));
vi.mock("@/hooks/useVaultEndpoints", () => ({
  useCreateEndpoint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateEndpoint: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { vaultEndpointsApi } from "@/lib/vault-endpoints";

const testApi = vi.mocked(vaultEndpointsApi.test);

describe("EndpointFormDialog — onglets + test par service", () => {
  beforeEach(() => testApi.mockReset());

  it("teste la vectorisation depuis son onglet (payload de la seule section)", async () => {
    testApi.mockResolvedValue({
      vectorization: { ok: true, message: "OK — vecteur de 1024 dimensions" },
      rerank: null,
      llm: null,
    });
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tester" }));

    await waitFor(() => expect(testApi).toHaveBeenCalled());
    const [vaultId, payload] = testApi.mock.calls[0]!;
    expect(vaultId).toBe("v1");
    expect(payload.indexer?.model).toBe("mxbai-embed-large");
    expect(payload.rerank).toBeNull();
    expect(payload.llm).toBeNull();

    expect(await screen.findByText(/vecteur de 1024 dimensions/)).toBeInTheDocument();
  });

  it("l'onglet LLM teste le LLM configuré", async () => {
    testApi.mockResolvedValue({
      vectorization: null,
      rerank: null,
      llm: { ok: true, message: "OK — réponse : pong" },
    });
    const endpoint = {
      id: "e1",
      vault_id: "v1",
      label: "Ollama",
      slug: "ollama",
      indexer: {
        provider: "ollama",
        model: "mxbai-embed-large",
        api_key_ref: null,
        base_url: "http://o:11434",
      },
      rerank: null,
      llm: { provider: "ollama", model: "qwen3:14b", api_key_ref: null, base_url: "http://o:11434" },
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    };
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={endpoint} open={true} onOpenChange={() => {}} />,
    );

    const llmTab = screen.getByRole("tab", { name: "LLM" });
    fireEvent.mouseDown(llmTab);
    fireEvent.click(llmTab);
    fireEvent.click(screen.getByRole("button", { name: "Tester" }));

    await waitFor(() => expect(testApi).toHaveBeenCalled());
    const [, payload] = testApi.mock.calls[0]!;
    expect(payload.indexer).toBeNull();
    expect(payload.llm?.model).toBe("qwen3:14b");
    expect(payload.llm?.provider).toBe("ollama");

    expect(await screen.findByText(/réponse : pong/)).toBeInTheDocument();
  });

  it("propose les modèles LLM de la TABLE DES MODÈLES (kind=llm)", async () => {
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );

    const llmTab = screen.getByRole("tab", { name: "LLM" });
    fireEvent.mouseDown(llmTab);
    fireEvent.click(llmTab);
    fireEvent.click(screen.getByRole("switch", { name: "LLM" }));

    // Le champ modèle est un Select alimenté par le registre (pas le serveur).
    expect(await screen.findByRole("combobox", { name: "Modèle LLM" })).toBeInTheDocument();
  });
});
