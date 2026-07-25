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

describe("EndpointFormDialog — bouton Tester", () => {
  beforeEach(() => testApi.mockReset());

  it("teste la config saisie et affiche les résultats", async () => {
    testApi.mockResolvedValue({
      vectorization: { ok: true, message: "OK — vecteur de 1024 dimensions" },
      rerank: { ok: false, message: "service rerank … : HTTP 404 — model not found" },
    });
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Tester" }));

    await waitFor(() => expect(testApi).toHaveBeenCalled());
    const [vaultId, payload] = testApi.mock.calls[0]!;
    expect(vaultId).toBe("v1");
    expect(payload.indexer.model).toBe("mxbai-embed-large");

    expect(await screen.findByText(/vecteur de 1024 dimensions/)).toBeInTheDocument();
    expect(screen.getByText(/model not found/)).toBeInTheDocument();
  });
});
