import { describe, it, expect, vi, beforeEach } from "vitest";
import { screen, fireEvent } from "@testing-library/react";
import { renderWithProviders } from "./testUtils";
import { WorkspaceSearchTab } from "@/pages/workspace/WorkspaceSearchTab";
import { ApiError } from "@/lib/api";
import { DEFAULT_HYBRID_SPEC } from "@/lib/search-config";
import type { HybridConfig, HybridSpec } from "@/lib/search-config.types";

const mockUseHybridConfig = vi.fn();
const mockMutate = vi.fn();

vi.mock("@/hooks/useSearchConfig", () => ({
  useHybridConfig: (...args: unknown[]) => mockUseHybridConfig(...args),
  useSaveHybridConfig: () => ({ mutate: mockMutate, isPending: false }),
}));

const baseConfig: HybridConfig = {
  workspace_id: "ws-1",
  enabled: true,
  rrf_k: 60,
  weight_lexical: 0.5,
  weight_vector: 0.5,
  lexical_engine: "fts",
  rebuild_job_id: null,
  created_at: "2026-07-01T10:00:00Z",
  updated_at: "2026-07-01T10:00:00Z",
};

describe("WorkspaceSearchTab", () => {
  beforeEach(() => {
    mockUseHybridConfig.mockReset();
    mockMutate.mockReset();
  });

  it("affiche l'état vectoriel pur quand la config est absente (404 → null)", () => {
    mockUseHybridConfig.mockReturnValue({ data: null, isLoading: false });
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    expect(screen.getByText("Recherche vectorielle pure")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Activer la recherche hybride" }),
    ).toBeInTheDocument();
    // Documentation ponctuelle + lien vers le manuel produit (docflow).
    expect(screen.getByText("Qu'est-ce que la recherche hybride ?")).toBeInTheDocument();
    expect(
      screen.getByRole("link", { name: /Documentation produit — Recherche hybride/ }),
    ).toHaveAttribute(
      "href",
      "https://doc.yoops.org/ws/ragflow/blocs/documentation/documents/de40ecfa-05d8-4de2-89b3-6fb142acdd01",
    );
  });

  it("active l'hybride avec les défauts depuis l'état vide", () => {
    mockUseHybridConfig.mockReturnValue({ data: null, isLoading: false });
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    fireEvent.click(screen.getByRole("button", { name: "Activer la recherche hybride" }));

    expect(mockMutate).toHaveBeenCalledWith(DEFAULT_HYBRID_SPEC, expect.anything());
  });

  it("charge une config existante dans le formulaire", () => {
    mockUseHybridConfig.mockReturnValue({
      data: { ...baseConfig, lexical_engine: "bm25", rrf_k: 42 },
      isLoading: false,
    });
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    expect(screen.getByRole("switch", { name: "Recherche hybride activée" })).toBeChecked();
    expect(screen.getByRole("radio", { name: /BM25 via extension pg_search/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /FTS natif Postgres/ })).not.toBeChecked();
    expect(screen.getByLabelText(/rrf_k/)).toHaveValue(42);
    expect(screen.getAllByText("50 %")).toHaveLength(2);
  });

  it("le PUT envoie le body complet avec les valeurs modifiées", () => {
    mockUseHybridConfig.mockReturnValue({ data: baseConfig, isLoading: false });
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    fireEvent.click(screen.getByRole("radio", { name: /BM25 via extension pg_search/ }));
    fireEvent.change(screen.getByRole("slider", { name: "Poids lexical" }), {
      target: { value: "0.7" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    const expected: HybridSpec = {
      enabled: true,
      rrf_k: 60,
      weight_lexical: 0.7,
      weight_vector: 0.5,
      lexical_engine: "bm25",
    };
    expect(mockMutate).toHaveBeenCalledWith(expected, expect.anything());
  });

  it("affiche le message pédagogique inline sur 422 lexical_engine_unavailable", () => {
    mockUseHybridConfig.mockReturnValue({ data: baseConfig, isLoading: false });
    mockMutate.mockImplementation(
      (_payload: HybridSpec, opts: { onError: (err: Error) => void }) => {
        opts.onError(
          new ApiError(422, {
            detail: {
              error: "lexical_engine_unavailable",
              engine: "bm25",
              hint: "CREATE EXTENSION pg_search;",
            },
          }),
        );
      },
    );
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(
      screen.getByText(/« bm25 » n'est pas disponible sur cette instance Postgres/),
    ).toBeInTheDocument();
    expect(screen.getByText("CREATE EXTENSION pg_search;")).toBeInTheDocument();
    expect(screen.getByText(/Installez l'extension pg_search/)).toBeInTheDocument();
  });

  it("affiche le bandeau de reconstruction quand le PUT renvoie un rebuild_job_id", () => {
    mockUseHybridConfig.mockReturnValue({ data: baseConfig, isLoading: false });
    mockMutate.mockImplementation(
      (_payload: HybridSpec, opts: { onSuccess: (config: HybridConfig) => void }) => {
        opts.onSuccess({ ...baseConfig, lexical_engine: "bm25", rebuild_job_id: "job-77" });
      },
    );
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);

    fireEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

    expect(
      screen.getByText("Reconstruction de l'index lexical lancée (job job-77)."),
    ).toBeInTheDocument();
  });

  it("interroge la config avec le nom du workspace et le flag enabled", () => {
    mockUseHybridConfig.mockReturnValue({ data: null, isLoading: false });
    renderWithProviders(<WorkspaceSearchTab name="ws-1" enabled />);
    expect(mockUseHybridConfig).toHaveBeenCalledWith("ws-1", true);
  });
});
