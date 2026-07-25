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
    data: [{ provider: "ollama", model: "mxbai-embed-large", dimension: 1024 }],
  }),
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

  it("l'onglet LLM teste le LLM saisi", async () => {
    testApi.mockResolvedValue({
      vectorization: null,
      rerank: null,
      llm: { ok: true, message: "OK — réponse : pong" },
    });
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );

    const llmTab = screen.getByRole("tab", { name: "LLM" });
    fireEvent.mouseDown(llmTab);
    fireEvent.click(llmTab);
    fireEvent.click(screen.getByRole("switch", { name: "LLM" }));
    fireEvent.change(screen.getByLabelText("Modèle LLM"), {
      target: { value: "qwen3:14b" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Tester" }));

    await waitFor(() => expect(testApi).toHaveBeenCalled());
    const [, payload] = testApi.mock.calls[0]!;
    expect(payload.indexer).toBeNull();
    expect(payload.llm?.model).toBe("qwen3:14b");
    expect(payload.llm?.provider).toBe("ollama");

    expect(await screen.findByText(/réponse : pong/)).toBeInTheDocument();
  });
});
