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

/** GET routé selon l'URL : partage enregistré + candidats. */
function mockGets(sharing: { shared_with_all: boolean; users: (typeof BOB)[] }) {
  vi.spyOn(apiModule.api, "get").mockImplementation((url: string) =>
    Promise.resolve(url.endsWith("/sharing") ? sharing : [BOB, CAROL]) as never,
  );
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

  it("pré-coche les bénéficiaires enregistrés et envoie la liste complète", async () => {
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

    const bob = await screen.findByRole("checkbox", { name: /bob@example.com/ });
    await waitFor(() => expect(bob).toBeChecked());
    fireEvent.click(screen.getByRole("checkbox", { name: /carol@example.com/ }));
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith("/api/admin/harpocrate-vaults/v-1/endpoints/ep-1/sharing", {
        shared_with_all: false,
        user_ids: ["u-bob", "u-carol"],
      }),
    );
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

    await screen.findByRole("checkbox", { name: /bob@example.com/ });
    fireEvent.click(screen.getByRole("switch", { name: "Partager avec tout le monde" }));
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    await waitFor(() =>
      expect(put).toHaveBeenCalledWith(expect.any(String), {
        shared_with_all: true,
        user_ids: [],
      }),
    );
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
