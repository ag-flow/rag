import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import { CreateWorkspaceDialog } from "@/pages/workspace/CreateWorkspaceDialog";
import type { UsableEndpointGroup } from "@/hooks/useVaultEndpoints";

const createMutateAsync = vi.fn();

vi.mock("@/hooks/useWorkspaces", () => ({
  useCreateWorkspace: () => ({ mutateAsync: createMutateAsync, isPending: false }),
}));

vi.mock("@/hooks/useVaultEndpoints", () => ({
  useUsableEndpoints: vi.fn(),
}));

vi.mock("@/hooks/useToast", () => ({
  useToast: () => ({ toast: vi.fn() }),
}));

import { useUsableEndpoints } from "@/hooks/useVaultEndpoints";

const GROUPED: UsableEndpointGroup[] = [
  {
    key: "v-1",
    vaultLabel: "Coffre RAG",
    endpoints: [
      {
        id: "ep-1",
        slug: "docs-openai",
        label: "Docs OpenAI",
        vault_id: "v-1",
        vault_name: "rag",
        vault_label: "Coffre RAG",
        access: "default",
        indexer: { provider: "openai", model: "text-embedding-3-small" },
        rerank: null,
        llm: null,
      },
    ],
  },
];

function mockEndpoints(data: UsableEndpointGroup[]): void {
  vi.mocked(useUsableEndpoints).mockReturnValue({
    data,
    isLoading: false,
  } as unknown as ReturnType<typeof useUsableEndpoints>);
}

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return (
    <MemoryRouter>
      <QueryClientProvider client={qc}>{children}</QueryClientProvider>
    </MemoryRouter>
  );
}

describe("CreateWorkspaceDialog (endpoint-based)", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("affiche label + sélecteur d'endpoint (unique pré-sélectionné)", () => {
    mockEndpoints(GROUPED);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByPlaceholderText("Mon projet")).toBeInTheDocument();
    // endpoint unique → pré-sélectionné et visible dans le trigger
    expect(screen.getByText(/Docs OpenAI — openai\/text-embedding-3-small/)).toBeInTheDocument();
  });

  it("nomme le coffre d'origine d'un endpoint partagé avec moi", () => {
    mockEndpoints([
      {
        key: "shared",
        vaultLabel: null,
        endpoints: [
          {
            id: "ep-alice",
            slug: "alice-ep",
            label: "Alice",
            vault_id: "v-alice",
            vault_name: "alice-vault",
            vault_label: "Coffre d'Alice",
            access: "shared",
            indexer: { provider: "openai", model: "text-embedding-3-small" },
            rerank: null,
            llm: null,
          },
        ],
      },
    ]);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(
      screen.getByText(/Alice — openai\/text-embedding-3-small · Coffre d'Alice/),
    ).toBeInTheDocument();
  });

  it("dérive le slug depuis le label saisi", () => {
    mockEndpoints(GROUPED);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    fireEvent.change(screen.getByPlaceholderText("Mon projet"), {
      target: { value: "Mon Super Projet !" },
    });
    // Le slug dérivé est affiché en lecture seule.
    expect(screen.getByText("mon-super-projet")).toBeInTheDocument();
  });

  it("soumet {name: slug, endpoint_id, label, description}", async () => {
    mockEndpoints(GROUPED);
    createMutateAsync.mockResolvedValue({ name: "mon-ws", label: "Mon WS" });
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    fireEvent.change(screen.getByPlaceholderText("Mon projet"), {
      target: { value: "Mon WS" },
    });
    fireEvent.change(screen.getByPlaceholderText(/optionnel/i), {
      target: { value: "Un corpus de test" },
    });
    fireEvent.click(screen.getByRole("button", { name: /^Créer$/i }));
    await waitFor(() =>
      expect(createMutateAsync).toHaveBeenCalledWith({
        name: "mon-ws",
        endpoint_id: "ep-1",
        label: "Mon WS",
        description: "Un corpus de test",
      }),
    );
  });

  it("sans endpoint : bouton Créer bloqué + lien vers les coffres", () => {
    mockEndpoints([]);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByText(/Aucun endpoint défini/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^Créer$/i })).toBeDisabled();
  });

  it("label vide : bouton Créer bloqué", () => {
    mockEndpoints(GROUPED);
    render(
      <Wrapper>
        <CreateWorkspaceDialog open onOpenChange={() => {}} />
      </Wrapper>,
    );
    expect(screen.getByRole("button", { name: /^Créer$/i })).toBeDisabled();
  });
});
