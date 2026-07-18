import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent, within } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { PlaygroundSearchTab } from "@/pages/workspace/PlaygroundSearchTab";
import type {
  ChannelHit,
  PlaygroundSearchRequest,
  PlaygroundSearchResponse,
} from "@/lib/search-config.types";

let mockData: PlaygroundSearchResponse | undefined;
const mockMutate = vi.fn();

vi.mock("@/hooks/useSearchConfig", () => ({
  usePlaygroundSearch: () => ({
    mutate: mockMutate,
    isPending: false,
    isError: false,
    data: mockData,
  }),
}));

const channelHit = (path: string, rank: number): ChannelHit => ({
  path,
  chunk_index: 0,
  rank,
  score: 0.9,
});

const response: PlaygroundSearchResponse = {
  query: "auth oidc",
  hybrid_enabled: true,
  rrf_k: 60,
  weight_vector: 0.7,
  weight_lexical: 0.3,
  lexical_engine: "fts",
  hits: [{ path: "a.md", chunk_index: 0, content: "Contenu du chunk A", score: 0.0163 }],
  vector_channel: [channelHit("a.md", 1), channelHit("b.md", 2)],
  lexical_channel: [channelHit("b.md", 1), channelHit("a.md", 2)],
};

function runSearch() {
  mockMutate.mockImplementation(
    (_payload: PlaygroundSearchRequest, opts: { onSuccess: (r: PlaygroundSearchResponse) => void }) => {
      mockData = response;
      opts.onSuccess(response);
    },
  );
  fireEvent.change(screen.getByLabelText("Requête de recherche…"), {
    target: { value: "auth oidc" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));
}

describe("PlaygroundSearchTab", () => {
  beforeEach(() => {
    mockData = undefined;
    mockMutate.mockReset();
  });

  it("lance une recherche et affiche les trois sections", () => {
    renderWithProviders(<PlaygroundSearchTab workspaceName="ws-1" />);
    runSearch();

    expect(mockMutate).toHaveBeenCalledWith({ query: "auth oidc" }, expect.anything());
    expect(screen.getByText("Fusion (RRF)")).toBeInTheDocument();
    expect(screen.getByText("Canal vectoriel")).toBeInTheDocument();
    expect(screen.getByText("Canal lexical")).toBeInTheDocument();
    expect(screen.getByText("Contenu du chunk A")).toBeInTheDocument();
  });

  it("initialise la simulation aux poids du serveur", () => {
    renderWithProviders(<PlaygroundSearchTab workspaceName="ws-1" />);
    runSearch();

    expect(screen.getByRole("slider", { name: "Poids vectoriel (simulation)" })).toHaveValue(
      "0.7",
    );
    expect(screen.getByRole("slider", { name: "Poids lexical (simulation)" })).toHaveValue("0.3");
  });

  it("refusionne côté client : un doc mieux classé lexicalement passe devant quand w_lexical monte", () => {
    renderWithProviders(<PlaygroundSearchTab workspaceName="ws-1" />);
    runSearch();

    const list = () => within(screen.getByRole("list", { name: "Fusion simulée" }));

    // Poids serveur (0.7 / 0.3) : a.md (rang 1 vectoriel) domine.
    expect(list().getAllByRole("listitem")[0]?.textContent).toContain("a.md");

    // On monte le poids lexical : b.md (rang 1 lexical) passe devant, sans rappel serveur.
    fireEvent.change(screen.getByRole("slider", { name: "Poids lexical (simulation)" }), {
      target: { value: "1" },
    });

    expect(list().getAllByRole("listitem")[0]?.textContent).toContain("b.md");
    expect(mockMutate).toHaveBeenCalledTimes(1);
  });

  it("affiche le bandeau hybride désactivé quand hybrid_enabled est false", () => {
    renderWithProviders(<PlaygroundSearchTab workspaceName="ws-1" />);
    mockMutate.mockImplementation(
      (
        _payload: PlaygroundSearchRequest,
        opts: { onSuccess: (r: PlaygroundSearchResponse) => void },
      ) => {
        const disabled = { ...response, hybrid_enabled: false, lexical_channel: [] };
        mockData = disabled;
        opts.onSuccess(disabled);
      },
    );
    fireEvent.change(screen.getByLabelText("Requête de recherche…"), {
      target: { value: "auth oidc" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Rechercher" }));

    expect(screen.getByText(/Recherche hybride non activée/)).toBeInTheDocument();
  });
});
