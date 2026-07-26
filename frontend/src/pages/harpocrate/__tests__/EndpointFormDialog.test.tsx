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
      {
        provider: "ollama",
        model: "bge-m3",
        kind: "embedding",
        dimension: 1024,
        url_template: "http://192.168.10.80:11434",
      },
      { provider: "ollama", model: "qwen3:14b", kind: "llm", dimension: null },
    ],
  }),
  useRerankPairings: () => ({ data: [] }),
  useProviderUrlTemplates: () => ({ data: {} }),
}));
vi.mock("@/hooks/useProviderKeys", () => ({
  useProviderKeys: () => ({ data: [] }),
}));
const { updateMutateAsync, vaultEndpointsData } = vi.hoisted(() => ({
  updateMutateAsync: vi.fn(),
  vaultEndpointsData: [] as unknown[],
}));
vi.mock("@/hooks/useVaultEndpoints", () => ({
  useCreateEndpoint: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useUpdateEndpoint: () => ({ mutateAsync: updateMutateAsync, isPending: false }),
  useVaultEndpoints: () => ({ data: vaultEndpointsData }),
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
      llm: {
        provider: "ollama",
        model: "qwen3:14b",
        api_key_ref: null,
        base_url: "http://o:11434",
      },
      fallback_endpoint_id: null,
      failure_threshold: 3,
      cooldown_seconds: 60,
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

  it("l'onglet Fallback n'existe qu'en édition et envoie les paramètres du breaker", async () => {
    updateMutateAsync.mockReset().mockResolvedValue(undefined);
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
      llm: null,
      fallback_endpoint_id: null,
      failure_threshold: 3,
      cooldown_seconds: 60,
      created_at: "2026-07-01T00:00:00Z",
      updated_at: "2026-07-01T00:00:00Z",
    };
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={endpoint} open={true} onOpenChange={() => {}} />,
    );

    const fallbackTab = screen.getByRole("tab", { name: "Fallback" });
    fireEvent.mouseDown(fallbackTab);
    fireEvent.click(fallbackTab);
    const threshold = await screen.findByRole("spinbutton", { name: "Échecs avant bascule" });
    expect(threshold).toHaveValue(3);
    fireEvent.change(threshold, { target: { value: "5" } });

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() => expect(updateMutateAsync).toHaveBeenCalled());
    const { payload } = updateMutateAsync.mock.calls[0]![0];
    expect(payload.clear_fallback).toBe(true); // aucun fallback sélectionné
    expect(payload.failure_threshold).toBe(5);
    expect(payload.cooldown_seconds).toBe(60);
  });

  it("pas d'onglet Fallback en création", () => {
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );
    expect(screen.queryByRole("tab", { name: "Fallback" })).not.toBeInTheDocument();
  });

  it("URL de paramétrage sans masque → préremplit la Base URL à la sélection du modèle", async () => {
    renderWithProviders(
      <EndpointFormDialog vaultId="v1" endpoint={null} open={true} onOpenChange={() => {}} />,
    );

    const modelSelect = screen.getByRole("combobox", { name: "Modèle" });
    fireEvent.mouseDown(modelSelect);
    fireEvent.click(modelSelect);
    fireEvent.click(await screen.findByRole("option", { name: "bge-m3" }));

    const baseUrlInputs = screen.getAllByPlaceholderText(/11434/);
    expect(baseUrlInputs[0]).toHaveValue("http://192.168.10.80:11434");
  });
});
