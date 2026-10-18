import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import i18n from "@/lib/i18n";
import * as apiModule from "@/lib/api";
import { groupUsableEndpoints } from "@/hooks/useVaultEndpoints";
import { EndpointShareDialog } from "@/pages/harpocrate/EndpointShareDialog";
import { VaultEndpointsTab } from "@/pages/harpocrate/VaultEndpointsTab";
import type { UsableEndpoint, VaultEndpoint } from "@/lib/vault-endpoints.types";

function Wrapper({ children }: { children: ReactNode }) {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

const EP: VaultEndpoint = {
  id: "ep-1",
  vault_id: "v-1",
  label: "Docs OpenAI",
  slug: "docs-openai",
  indexer: { provider: "openai", model: "text-embedding-3-small", api_key_ref: null, base_url: null },
  rerank: null,
  llm: null,
  fallback_endpoint_id: null,
  failure_threshold: 3,
  cooldown_seconds: 60,
  shared_with_all: false,
  shared_user_count: 0,
  created_at: "2026-10-18T00:00:00Z",
  updated_at: "2026-10-18T00:00:00Z",
};

const BOB = { id: "u-bob", username: "bob", email: "bob@example.com" };
const CAROL = { id: "u-carol", username: "carol@example.com", email: "carol@example.com" };

function usable(id: string, access: UsableEndpoint["access"], vault: string): UsableEndpoint {
  return {
    id,
    slug: id,
    label: id,
    vault_id: vault,
    vault_name: vault,
    vault_label: `Coffre ${vault}`,
    access,
    indexer: { provider: "openai", model: "m" },
    rerank: null,
    llm: null,
  };
}

/** GET routé selon l'URL : partage enregistré + recherche par email exact. */
function mockGets(sharing: { shared_with_all: boolean; users: (typeof BOB)[] }) {
  vi.spyOn(apiModule.api, "get").mockImplementation((url: string) => {
    if (url.endsWith("/sharing")) return Promise.resolve(sharing) as never;
    if (url.includes("email=carol%40example.com")) return Promise.resolve(CAROL) as never;
    return Promise.reject(new Error("404")) as never;
  });
}

describe("groupUsableEndpoints", () => {
  it("groupe par coffre et isole les endpoints partagés dans un groupe final", () => {
    const groups = groupUsableEndpoints([
      usable("a", "owned", "v1"),
      usable("s1", "shared", "v9"),
      usable("b", "default", "v2"),
      usable("s2", "shared", "v8"),
    ]);
    expect(groups.map((g) => [g.vaultLabel, g.endpoints.map((e) => e.id)])).toEqual([
      ["Coffre v1", ["a"]],
      ["Coffre v2", ["b"]],
      [null, ["s1", "s2"]],
    ]);
  });
});

describe("EndpointShareDialog", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("ajoute un bénéficiaire par email exact et envoie la liste complète", async () => {
    mockGets({ shared_with_all: false, users: [BOB] });
    const put = vi.spyOn(apiModule.api, "put").mockResolvedValue({
      shared_with_all: false,
      users: [BOB, CAROL],
    } as never);
    render(
      <Wrapper>
        <EndpointShareDialog vaultId="v-1" endpoint={EP} onOpenChange={() => {}} />
      </Wrapper>,
    );

    expect(await screen.findByText("bob@example.com")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Email exact de l'utilisateur"), {
      target: { value: "carol@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ajouter" }));
    expect(await screen.findByText("carol@example.com")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/admin/harpocrate-vaults/v-1/endpoints/ep-1/sharing", {
        shared_with_all: false,
        user_ids: ["u-bob", "u-carol"],
      }),
    );
  });

  it("signale un email inconnu sans rien ajouter", async () => {
    mockGets({ shared_with_all: false, users: [] });
    render(
      <Wrapper>
        <EndpointShareDialog vaultId="v-1" endpoint={EP} onOpenChange={() => {}} />
      </Wrapper>,
    );

    fireEvent.change(await screen.findByLabelText("Email exact de l'utilisateur"), {
      target: { value: "ghost@example.com" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Ajouter" }));

    expect(await screen.findByText(/Aucun utilisateur avec cet email/)).toBeInTheDocument();
    expect(screen.getByText("Aucun bénéficiaire.")).toBeInTheDocument();
  });

  it("retire un bénéficiaire", async () => {
    mockGets({ shared_with_all: false, users: [BOB] });
    render(
      <Wrapper>
        <EndpointShareDialog vaultId="v-1" endpoint={EP} onOpenChange={() => {}} />
      </Wrapper>,
    );

    fireEvent.click(await screen.findByRole("button", { name: "Retirer bob@example.com" }));
    expect(screen.queryByText("bob@example.com")).not.toBeInTheDocument();
  });

  it("partage à tous : masque la liste et n'envoie aucun bénéficiaire nommé", async () => {
    mockGets({ shared_with_all: false, users: [BOB] });
    const put = vi.spyOn(apiModule.api, "put").mockResolvedValue({
      shared_with_all: true,
      users: [],
    } as never);
    render(
      <Wrapper>
        <EndpointShareDialog vaultId="v-1" endpoint={EP} onOpenChange={() => {}} />
      </Wrapper>,
    );

    await screen.findByText("bob@example.com");
    fireEvent.click(screen.getByRole("switch", { name: "Partager avec tout le monde" }));
    expect(screen.queryByText("bob@example.com")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(expect.any(String), {
        shared_with_all: true,
        user_ids: [],
      }),
    );
  });
});

describe("VaultEndpointsTab — dialogue de partage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("une sélection annulée ne réapparaît pas à la réouverture", async () => {
    vi.spyOn(apiModule.api, "get").mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("/health")
          ? {}
          : url.endsWith("/sharing")
            ? { shared_with_all: false, users: [BOB] }
            : [EP],
      ) as never,
    );
    render(
      <Wrapper>
        <VaultEndpointsTab vaultId="v-1" />
      </Wrapper>,
    );
    fireEvent.click(await screen.findByRole("button", { name: "Partager" }));
    fireEvent.click(await screen.findByRole("button", { name: "Retirer bob@example.com" }));
    fireEvent.click(screen.getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: "Partager" }));
    expect(await screen.findByText("bob@example.com")).toBeInTheDocument();
  });
});

describe("VaultEndpointsTab — badge de partage", () => {
  beforeEach(async () => {
    vi.restoreAllMocks();
    await i18n.changeLanguage("fr");
  });

  it("affiche « Tout le monde » ou le nombre de bénéficiaires", async () => {
    vi.spyOn(apiModule.api, "get").mockImplementation((url: string) =>
      Promise.resolve(
        url.endsWith("/health")
          ? {}
          : [
              { ...EP, id: "ep-all", label: "A", shared_with_all: true },
              { ...EP, id: "ep-two", label: "B", shared_user_count: 2 },
            ],
      ) as never,
    );
    render(
      <Wrapper>
        <VaultEndpointsTab vaultId="v-1" />
      </Wrapper>,
    );
    expect(await screen.findByText("Tout le monde")).toBeInTheDocument();
    expect(screen.getByText("2 personnes")).toBeInTheDocument();
  });
});
